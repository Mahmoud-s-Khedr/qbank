import base64
import json
import zipfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document
from docx.table import Table
from PIL import Image

from qbank.export import make_reference_docx
from qbank.export.mhchem import ce_to_tex, convert_math
from qbank.export.pandoc_ast import NBSP, Context, blocks_qmd, inline_qmd
from qbank.export.view import (
    ChoiceView,
    ExamView,
    GroupView,
    HeaderView,
    QuestionView,
    SectionView,
    StimulusView,
    arabic_digits,
    auto_choices_per_row,
)
from qbank.export.word import reference_path, render_answer_key_docx, render_docx
from qbank.schemas.exams import AnswerKey, AnswerKeyEntry, ExamLayout

SHORT, MEDIUM, LONG = "x" * 5, "x" * 30, "x" * 60  # 4, 2 and 1 per row
EXPECTED_FONT_SIZE = 14
PIXELS = 240
LIST_START = 3


def figure_uri() -> str:
    buffer = BytesIO()
    Image.new("RGB", (PIXELS, 140), (30, 90, 200)).save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def resolver(asset_id: str) -> str | None:
    return figure_uri() if asset_id == "known" else None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (r"\ce{H2O}", r"\mathrm{H_2O}"),
        (r"\ce{2H2 + O2 -> 2H2O}", r"\mathrm{2H_2 + O_2 \rightarrow 2H_2O}"),
        (r"\ce{SO4^2-}", r"\mathrm{SO_4^{2-}}"),
        (r"\ce{SO4^{2-}}", r"\mathrm{SO_4^{2-}}"),
        (r"\ce{Na+ + Cl- -> NaCl(s)}", r"\mathrm{Na^+ + Cl^- \rightarrow NaCl(s)}"),
        (r"\ce{Fe2+}", r"\mathrm{Fe^{2+}}"),
        (r"\ce{Ca(OH)2(aq)}", r"\mathrm{Ca(OH)_2(aq)}"),
        (
            r"\ce{N2(g) + 3H2(g) <=> 2NH3(g)}",
            r"\mathrm{N_2(g) + 3H_2(g) \rightleftharpoons 2NH_3(g)}",
        ),
        (r"\ce{A <-> B}", r"\mathrm{A \leftrightarrow B}"),
        (r"\ce{A <- B}", r"\mathrm{A \leftarrow B}"),
        (r"\ce{C12H22O11}", r"\mathrm{C_{12}H_{22}O_{11}}"),
        (r"\ce{A->B}", r"\mathrm{A\rightarrow B}"),
        (r"\ce{CuSO4*5H2O}", r"\mathrm{CuSO_4\cdot 5H_2O}"),
        (r"\ce{x_2 + y^2}", r"\mathrm{x_{2} + y^{2}}"),
    ],
)
def test_mhchem_patterns(source: str, expected: str) -> None:
    assert convert_math(source) == expected


def test_mhchem_unknown_constructs_fall_back_to_raw_text() -> None:
    assert convert_math(r"\ce{A\bond{-}B}") == r"\mathrm{A\backslash bond\{-\}B}"
    assert ce_to_tex("a & b ~ c") == r"\mathrm{a \& b \~{} c}"
    assert convert_math(r"\ce{H2O") == r"\ce{H2O"  # unbalanced: left alone
    assert convert_math(r"x+\ce{CO2}=\ce{O2}") == r"x+\mathrm{CO_2}=\mathrm{O_2}"
    assert convert_math("no chemistry") == "no chemistry"


def ctx(tmp_path: Path) -> Context:
    return Context(media_dir=tmp_path, assets=resolver)


def test_qmd_math_passes_through_as_tex_with_chemistry_converted(tmp_path: Path) -> None:
    blocks = blocks_qmd("a $x^2$ b $$y$$ c $\\ce{H2O}$\n\n$$\\frac{1}{2}$$", ctx(tmp_path))
    dumped = json.dumps(blocks, ensure_ascii=False)
    assert '"InlineMath"' in dumped
    assert '"DisplayMath"' in dumped
    assert "x^2" in dumped
    assert r"\\mathrm{H_2O}" in dumped
    assert r"\\ce" not in dumped


def test_qmd_assets_are_written_and_capped(tmp_path: Path) -> None:
    blocks = blocks_qmd(
        "![fig](asset:known) ![gone](asset:nope) ![web](https://x/y.png)", ctx(tmp_path)
    )
    (paragraph,) = blocks
    images = [n for n in paragraph["c"] if n["t"] == "Image"]
    (image,) = images
    attrs, _, (target, _) = image["c"]
    assert Path(target).read_bytes().startswith(b"\x89PNG")
    width = float(dict(attrs[2])["width"].removesuffix("in"))
    assert width == pytest.approx(PIXELS / 96)  # natural size, below the 60% cap
    assert [n["c"] for n in paragraph["c"] if n["t"] == "Str" and n["c"].startswith("[")] == [
        "[figure]",
        "[figure]",
    ]


def test_qmd_large_images_are_capped_and_bad_data_is_ignored(tmp_path: Path) -> None:
    buffer = BytesIO()
    Image.new("RGB", (2000, 100)).save(buffer, "PNG")
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    context = Context(media_dir=tmp_path, assets=lambda _: uri)
    (paragraph,) = blocks_qmd("![](asset:big)", context)
    assert dict(paragraph["c"][0]["c"][0][2])["width"] == "4.00in"
    assert (
        Context(media_dir=tmp_path, assets=lambda _: "data:image/png;base64,A").image("a") is None
    )
    assert Context(media_dir=tmp_path).image("a") is None
    assert Context(media_dir=tmp_path, assets=lambda _: "http://x").image("a") is None


def test_qmd_blanks_become_underlined_spaces(tmp_path: Path) -> None:
    (paragraph,) = blocks_qmd("املأ ____ هنا", ctx(tmp_path))
    underlined = [n for n in paragraph["c"] if n["t"] == "Underline"]
    assert len(underlined) == 1
    assert set(underlined[0]["c"][0]["c"]) == {NBSP}
    assert "____" not in json.dumps(paragraph)
    rule = blocks_qmd("____", ctx(tmp_path))
    assert rule[0]["t"] == "Para"
    assert rule[0]["c"][0]["t"] == "Underline"
    assert blocks_qmd("---", ctx(tmp_path))[0]["t"] == "HorizontalRule"


def test_qmd_never_emits_raw_html_or_tex(tmp_path: Path) -> None:
    source = (
        '<script>alert(1)</script> <b>x</b>\n\n<div onclick="x">y</div>\n\n[l](javascript:alert(1))'
    )
    dumped = json.dumps(blocks_qmd(source, ctx(tmp_path)))
    assert "RawBlock" not in dumped
    assert "RawInline" not in dumped
    assert "Link" not in dumped  # links keep their text only


def test_qmd_structures(tmp_path: Path) -> None:
    source = (
        "# H\n\n- a\n- b *i* **s** ~~x~~ `c`\n\n3. one\n4. two\n\n> quote\n\n```\ncode\n```\n\n"
        "| h1 | h2 |\n|---|---|\n| c1 | c2 |\n\nline  \nbreak\nsoft"
    )
    blocks = blocks_qmd(source, ctx(tmp_path))
    kinds = [b["t"] for b in blocks]
    assert kinds == [
        "Header",
        "BulletList",
        "OrderedList",
        "BlockQuote",
        "CodeBlock",
        "Table",
        "Para",
    ]
    assert blocks[2]["c"][0][0] == LIST_START
    dumped = json.dumps(blocks)
    for tag in ("Emph", "Strong", "Strikeout", "Code", "LineBreak", "SoftBreak"):
        assert tag in dumped
    assert inline_qmd("", ctx(tmp_path)) == []
    assert inline_qmd("a $b$", ctx(tmp_path))[-1]["t"] == "Math"
    assert [n["t"] for n in inline_qmd("*open", ctx(tmp_path))] == ["Str"]


def choices(*contents: str) -> list[ChoiceView]:
    return [ChoiceView("أبجد"[i], c) for i, c in enumerate(contents)]


def exam(
    questions: list[QuestionView],
    *,
    language: str = "ar",
    layout: ExamLayout | None = None,
    groups: list[GroupView] | None = None,
    header: HeaderView | None = None,
) -> ExamView:
    return ExamView(
        language=language,
        version_label="ب",
        header=header
        or HeaderView(
            school_name="مدرسة النور",
            exam_title="اختبار الرياضيات",
            subject="رياضيات",
            grade="3",
            date="2026-01-02",
            duration_minutes=45,
            instructions="اقرأ **جيداً**",
        ),
        layout=layout or ExamLayout(),
        sections=[
            SectionView("القسم الأول", "ملاحظة", groups or [GroupView(questions=questions)]),
        ],
    )


def tables_of(data: bytes) -> list[Table]:
    return list(Document(BytesIO(data)).tables)


def choice_tables(data: bytes) -> list[Table]:
    return [t for t in tables_of(data) if t.style is not None and t.style.name == "PlainTable"][1:]


@pytest.mark.parametrize(
    ("contents", "setting"),
    [
        ((SHORT,) * 4, "auto"),
        ((MEDIUM,) * 4, "auto"),
        ((LONG,) * 4, "auto"),
        ((SHORT,) * 4, 2),
        ((LONG,) * 4, 4),
    ],
)
def test_choice_table_columns_follow_the_pdf_rule(
    contents: tuple[str, ...], setting: str | int
) -> None:
    question = QuestionView(1, "mcq_single", "q", 1, choices(*contents))
    data = render_docx(exam([question], layout=ExamLayout(choices_per_row=setting)))
    (table,) = choice_tables(data)
    expected = auto_choices_per_row(contents) if setting == "auto" else int(setting)
    assert len(table.columns) == expected
    assert len(table.rows) == -(-len(contents) // expected)
    labels = [c.text.split()[0] for r in table.rows for c in r.cells if c.text]
    assert labels == list("أبجد")


def test_header_structure_arabic_digits_and_rtl(tmp_path: Path) -> None:
    questions = [
        QuestionView(7, "mcq_single", "ما $x$ ؟", 2, choices("1", "2")),
        QuestionView(8, "essay", "اشرح", 1.5),
        QuestionView(9, "true_false", "صح؟", 1),
    ]
    data = render_docx(exam(questions), resolver)
    document = Document(BytesIO(data))
    header = " ".join(c.text for c in document.tables[0]._cells)
    for expected in (
        "رياضيات",
        arabic_digits("3"),
        arabic_digits("2026-01-02"),
        arabic_digits("45") + " دقيقة",
        "الدرجة الكلية: " + arabic_digits("4.5"),
        "النموذج: ب",
    ):
        assert expected in header
    texts = [p.text for p in document.paragraphs]
    assert "مدرسة النور" in texts
    assert "اختبار الرياضيات" in texts
    assert any(
        t.startswith(arabic_digits("7") + "- ما") and f"({arabic_digits('2')} درجات)" in t
        for t in texts
    )
    assert any(
        t.startswith(arabic_digits("8") + "- اشرح") and f"({arabic_digits('1.5')} درجات)" in t
        for t in texts
    )
    assert any("صح" in t and "خطأ" in t and "☐" in t for t in texts)
    assert (
        sum(1 for p in document.paragraphs if p.style is not None and p.style.name == "AnswerLine")
        == ExamLayout().answer_space_lines
    )
    xml = zipfile.ZipFile(BytesIO(data)).read("word/document.xml").decode()
    assert "<w:bidi/>" in xml
    assert xml.count("<w:bidiVisual/>") == len(document.tables)
    assert "m:oMath" in xml


def test_english_exam_is_ltr_and_honours_font_size_and_stimulus() -> None:
    stimulus = StimulusView("passage", "A train goes $120$ km.", None)
    group = GroupView(
        [QuestionView(1, "mcq_single", "q", 1, [ChoiceView("a", "x"), ChoiceView("b", "y")])],
        stimulus,
    )
    view = exam(
        [],
        language="en",
        layout=ExamLayout(font_size_pt=EXPECTED_FONT_SIZE, digits="arabic"),
        groups=[group],
        header=HeaderView(exam_title="Maths"),
    )
    data = render_docx(view)
    xml = zipfile.ZipFile(BytesIO(data)).read("word/document.xml").decode()
    assert "<w:bidi" not in xml
    document = Document(BytesIO(data))
    assert document.styles["Normal"].font.size is not None
    assert document.styles["Normal"].font.size.pt == EXPECTED_FONT_SIZE
    texts = [p.text for p in document.paragraphs]
    assert "Read the text, then answer the questions that follow" in texts
    assert any(t.startswith("1- q") and "(1 mark)" in t for t in texts)
    assert document.core_properties.title == "Maths"


def test_answer_key_docx_rows_and_missing_key() -> None:
    key = AnswerKey(
        label="ب",
        warnings=[],
        items=[
            AnswerKeyEntry(
                number=1,
                question_id=uuid4(),
                type="mcq_single",
                correct=["أ", "ج"],
                answer_text=None,
                points=2,
            ),
            AnswerKeyEntry(
                number=2,
                question_id=uuid4(),
                type="essay",
                correct=None,
                answer_text="لأن $x$",
                points=3,
            ),
            AnswerKeyEntry(
                number=3,
                question_id=uuid4(),
                type="essay",
                correct=None,
                answer_text=None,
                points=1,
            ),
        ],
    )
    view = exam([QuestionView(1, "mcq_single", "q", 2, choices("1", "2"))])
    data = render_answer_key_docx(view.with_key(key))
    (table,) = tables_of(data)
    rows = [[c.text for c in r.cells] for r in table.rows]
    assert rows[0] == ["رقم السؤال", "الإجابة الصحيحة", "الدرجة"]
    ar = arabic_digits
    assert rows[1] == [ar("1"), "أ، ج", ar("2")]
    assert rows[2][0] == ar("2")
    assert rows[3] == [ar("3"), "—", ar("1")]
    assert rows[4][0] == "الدرجة الكلية"
    assert rows[4][2] == ar("6")
    assert "m:oMath" in zipfile.ZipFile(BytesIO(data)).read("word/document.xml").decode()
    with pytest.raises(ValueError, match="answer key missing"):
        render_answer_key_docx(view)


def test_logo_is_embedded_in_header() -> None:
    header = HeaderView(exam_title="t", logo_uri=figure_uri())
    data = render_docx(exam([QuestionView(1, "essay", "q", 1)], header=header))
    names = zipfile.ZipFile(BytesIO(data)).namelist()
    assert len([n for n in names if n.startswith("word/media/")]) == 1


def part(data: bytes, name: str) -> bytes:
    return zipfile.ZipFile(BytesIO(data)).read(name)


@pytest.mark.parametrize("language", ["ar", "en"])
def test_reference_docx_is_reproducible_and_committed(language: str) -> None:
    first, second = make_reference_docx.build(language), make_reference_docx.build(language)
    committed = reference_path(language).read_bytes()
    for name in ("word/styles.xml", "word/document.xml", "word/footer1.xml"):
        assert part(first, name) == part(second, name) == part(committed, name)


def test_reference_docx_styles() -> None:
    rtl = Document(str(reference_path("ar")))
    ltr = Document(str(reference_path("en")))
    section = rtl.sections[0]
    assert section.page_width is not None
    assert section.page_height is not None
    assert section.left_margin is not None
    assert section.page_width.cm == pytest.approx(21.0, abs=0.01)
    assert section.page_height.cm == pytest.approx(29.7, abs=0.01)
    assert section.left_margin.cm == pytest.approx(2.0, abs=0.01)
    rtl_styles = part(reference_path("ar").read_bytes(), "word/styles.xml").decode()
    ltr_styles = part(reference_path("en").read_bytes(), "word/styles.xml").decode()
    assert "Noto Naskh Arabic" in rtl_styles
    assert "w:cs=" in rtl_styles
    assert "<w:bidi/>" in rtl_styles
    assert "<w:bidi/>" not in ltr_styles
    for name in (
        "ExamTitle",
        "Question",
        "AnswerLine",
        "Stimulus",
        "Points",
        "PlainTable",
        "Table",
    ):
        assert name in rtl.styles
        assert name in ltr.styles


def test_reference_docx_cli_writes_both_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(make_reference_docx, "OUT_DIR", tmp_path / "out")
    make_reference_docx.main()
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "reference-ltr.docx",
        "reference-rtl.docx",
    ]
