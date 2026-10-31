"""Exam views to editable ``.docx`` bytes through Pandoc (native OMML equations, RTL for Arabic).

The layout decisions (numbering, lettering, choice columns, digits) come from the same
``ExamView`` the PDF uses. This module only maps that view onto a Pandoc document.
"""

import json
import tempfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import pypandoc  # type: ignore[import-untyped]  # pypandoc ships no type stubs
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from qbank.export import pandoc_ast as ast
from qbank.export.pandoc_ast import NBSP, Context, Node
from qbank.export.qmd import AssetResolver
from qbank.export.render import STRINGS
from qbank.export.view import (
    ExamView,
    GroupView,
    QuestionView,
    SectionView,
    choices_per_row,
    digits_formatter,
)

REFERENCE_DIR = Path(__file__).parent / "reference"
HEADER_COLUMNS = 3
CHECKBOX = "☐"
GAP = NBSP * 6
LOGO_WIDTH = "1.1in"
KEY_WIDTHS = [0.2, 0.6, 0.2]


def reference_path(language: str) -> Path:
    return REFERENCE_DIR / f"reference-{'rtl' if language == 'ar' else 'ltr'}.docx"


class _Builder:
    def __init__(self, view: ExamView, ctx: Context) -> None:
        self.view, self.ctx = view, ctx
        self.t = STRINGS[view.language]
        self.d: Callable[[object], str] = digits_formatter(view.language, view.layout.digits)
        self.rtl = view.language == "ar"

    # --- small helpers -----------------------------------------------------------------------

    def labelled(self, label: str, value: str) -> list[Node]:
        return [*ast.text(f"{label}:"), node_space(), strong(value)]

    def points(self, q: QuestionView) -> Node:
        unit = self.t["mark"] if q.points == 1 else self.t["marks"]
        return ast.styled_span(ast.text(f"({self.d(q.points)} {unit})"), "Points")

    # --- exam --------------------------------------------------------------------------------

    def header(self) -> list[Node]:
        h, t = self.view.header, self.t
        out: list[Node] = []
        logo = self.ctx.from_uri(h.logo_uri)
        if logo:
            picture = ast.node(
                "Image", [ast.attr(pairs={"width": LOGO_WIDTH}), [], [str(logo), ""]]
            )
            out.append(ast.div([ast.para([picture])], "ExamSchool"))
        if h.school_name:
            out.append(ast.div([ast.para(ast.text(h.school_name))], "ExamSchool"))
        out.append(ast.div([ast.para(ast.text(h.exam_title))], "ExamTitle"))
        fields: list[list[Node]] = []
        if h.subject:
            fields.append(self.labelled(t["subject"], h.subject))
        if h.grade:
            fields.append(self.labelled(t["grade"], self.d(h.grade)))
        if h.date:
            fields.append(self.labelled(t["date"], self.d(h.date)))
        if h.duration_minutes:
            fields.append(
                self.labelled(t["duration"], f"{self.d(h.duration_minutes)} {t['minutes']}")
            )
        fields.append(self.labelled(t["total"], self.d(self.view.total_points)))
        fields.append(self.labelled(t["version"], self.view.version_label))
        rows = [
            [[ast.node("Plain", f)] for f in fields[i : i + HEADER_COLUMNS]]
            for i in range(0, len(fields), HEADER_COLUMNS)
        ]
        out.append(ast.table(rows, style="Table", widths=[1 / HEADER_COLUMNS] * HEADER_COLUMNS))
        student = [
            [ast.node("Plain", [*ast.text(f"{t[k]}:"), node_space(), ast.blank()])]
            for k in ("student_name", "student_number", "class")
        ]
        out.append(ast.para([]))
        out.append(ast.table([student], style="PlainTable", widths=[1 / 3] * 3))
        if h.instructions:
            body = [
                ast.para([strong(t["instructions"])]),
                *ast.blocks_qmd(h.instructions, self.ctx),
            ]
            out.append(ast.div(body, "Instructions"))
        return out

    def choices(self, q: QuestionView) -> Node:
        per_row = choices_per_row(self.view.layout.choices_per_row, [c.content for c in q.choices])
        cells = [
            [
                ast.node(
                    "Plain",
                    [strong(c.label), node_space(), *ast.inline_qmd(c.content, self.ctx)],
                )
            ]
            for c in q.choices
        ]
        rows = [cells[i : i + per_row] for i in range(0, len(cells), per_row)]
        return ast.table(rows, style="PlainTable", widths=[1 / per_row] * per_row)

    def question(self, q: QuestionView) -> list[Node]:
        blocks = ast.blocks_qmd(q.stem, self.ctx)
        lead = [strong(f"{self.d(q.number)}-"), node_space()]
        if blocks and blocks[0]["t"] in {"Para", "Plain"}:
            blocks[0] = ast.para([*lead, *blocks[0]["c"]])
        else:
            blocks.insert(0, ast.para(lead))
        last = blocks[-1]
        if last["t"] in {"Para", "Plain"}:
            last["c"] = [*last["c"], node_space(), self.points(q)]
        else:
            blocks.append(ast.para([self.points(q)]))
        out = [ast.div(blocks, "Question")]
        if q.choices:
            out.append(self.choices(q))
        elif q.type == "true_false":
            t = self.t
            marks = f"{CHECKBOX} {t['true']}{GAP}{CHECKBOX} {t['false']}"
            out.append(ast.para(ast.text(marks.replace(" ", NBSP, 1))))
        if q.has_lines:
            line = ast.div([ast.para([ast.node("Str", NBSP)])], "AnswerLine")
            out.extend(line for _ in range(self.view.layout.answer_space_lines))
        return out

    def group(self, group: GroupView) -> list[Node]:
        out: list[Node] = []
        if group.stimulus:
            intro = group.stimulus.intro or self.t["intro"]
            body = [
                ast.div([ast.para([strong(intro)])], "StimulusIntro"),
                *ast.blocks_qmd(group.stimulus.content, self.ctx),
            ]
            out.append(ast.div(body, "Stimulus"))
        for q in group.questions:
            out.extend(self.question(q))
        return out

    def section(self, section: SectionView) -> list[Node]:
        out: list[Node] = []
        if section.title:
            out.append(ast.node("Header", [2, ast.attr(), ast.text(section.title)]))
        if section.instructions:
            out.append(ast.div(ast.blocks_qmd(section.instructions, self.ctx), "SectionNote"))
        for group in section.groups:
            out.extend(self.group(group))
        return out

    def exam(self) -> list[Node]:
        out = self.header()
        for section in self.view.sections:
            out.extend(self.section(section))
        return out

    # --- answer key --------------------------------------------------------------------------

    def answer_key(self) -> list[Node]:
        key, t = self.view.key, self.t
        if key is None:
            raise ValueError("answer key missing")
        sep = "، " if self.rtl else ", "
        rows: list[list[list[Node]]] = []
        for e in key.items:
            if e.correct:
                answer = ast.text(sep.join(e.correct))
            elif e.answer_text:
                answer = ast.inline_qmd(e.answer_text, self.ctx)
            else:
                answer = ast.text("—")
            rows.append(
                [
                    [ast.node("Plain", ast.text(self.d(e.number)))],
                    [ast.node("Plain", answer)],
                    [ast.node("Plain", ast.text(self.d(e.points)))],
                ]
            )

        def head(label: str) -> list[Node]:
            return [ast.node("Plain", [strong(label)])]

        total = sum(e.points for e in key.items)
        footer = [
            [ast.node("Plain", [strong(t["total"])])],
            [],
            [ast.node("Plain", [strong(self.d(total))])],
        ]
        sub = f"{self.view.header.exam_title} — {t['version']}: "
        return [
            ast.div([ast.para(ast.text(t["key_title"]))], "ExamTitle"),
            ast.div([ast.para([*ast.text(sub), strong(self.view.version_label)])], "ExamSchool"),
            ast.table(
                rows,
                style="Table",
                header=[head(t["number"]), head(t["answer"]), head(t["points"])],
                footer=footer,
                widths=KEY_WIDTHS,
            ),
        ]


def strong(value: str) -> Node:
    return ast.node("Strong", ast.text(value))


def node_space() -> Node:
    return ast.node("Space")


def _postprocess(data: bytes, view: ExamView) -> bytes:
    """Things Pandoc does not do: table column order for RTL, base font size, core properties."""
    document = Document(BytesIO(data))
    if view.language == "ar":
        for table in document.element.body.iter(qn("w:tbl")):
            properties = table.find(qn("w:tblPr"))
            if properties is not None and properties.find(qn("w:bidiVisual")) is None:
                visual = OxmlElement("w:bidiVisual")
                style = properties.find(qn("w:tblStyle"))
                if style is not None:
                    style.addnext(visual)
                else:
                    properties.insert(0, visual)
    size = Pt(view.layout.font_size_pt)
    normal = document.styles["Normal"]
    normal.font.size = size
    fonts = normal.element.get_or_add_rPr()
    complex_size = fonts.find(qn("w:szCs"))
    if complex_size is None:
        complex_size = OxmlElement("w:szCs")
        fonts.append(complex_size)
    complex_size.set(qn("w:val"), str(view.layout.font_size_pt * 2))
    document.core_properties.title = view.header.exam_title
    document.core_properties.language = view.language
    document.core_properties.author = view.header.school_name or "Qbank"
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def _convert(blocks: list[Node], view: ExamView, workdir: Path) -> bytes:
    body = [ast.div(blocks, direction="rtl")] if view.language == "ar" else blocks
    source = json.dumps(ast.document(body, view.language), ensure_ascii=False)
    target = workdir / "out.docx"
    pypandoc.convert_text(
        source,
        "docx",
        format="json",
        outputfile=str(target),
        extra_args=[
            f"--reference-doc={reference_path(view.language)}",
            f"--resource-path={workdir}",
        ],
    )
    return _postprocess(target.read_bytes(), view)


def render_docx(view: ExamView, assets: AssetResolver | None = None) -> bytes:
    with tempfile.TemporaryDirectory(prefix="qbank-docx-") as tmp:
        workdir = Path(tmp)
        ctx = Context(media_dir=workdir, assets=assets)
        return _convert(_Builder(view, ctx).exam(), view, workdir)


def render_answer_key_docx(view: ExamView, assets: AssetResolver | None = None) -> bytes:
    with tempfile.TemporaryDirectory(prefix="qbank-docx-") as tmp:
        workdir = Path(tmp)
        ctx = Context(media_dir=workdir, assets=assets)
        return _convert(_Builder(view, ctx).answer_key(), view, workdir)
