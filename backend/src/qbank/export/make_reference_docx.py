"""Builds the Pandoc ``reference.docx`` files (RTL for Arabic, LTR for English) from code.

Run ``uv run python -m qbank.export.make_reference_docx`` from ``backend/`` to regenerate
``export/reference/reference-{rtl,ltr}.docx``. The files patch Pandoc's own default reference doc:
fonts, sizes, RTL, A4 with 2 cm margins, the custom paragraph/character/table styles that
``export/word.py`` refers to by name, and a page-number footer.
"""

import subprocess
from io import BytesIO
from pathlib import Path

import pypandoc  # type: ignore[import-untyped]  # pypandoc ships no type stubs
from docx import Document
from docx.document import Document as DocumentType
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Twips
from docx.styles.style import BaseStyle
from docx.text.paragraph import Paragraph

OUT_DIR = Path(__file__).parent / "reference"
ARABIC_FONT = "Noto Naskh Arabic"
LATIN_FONT = "Arial"
A4_WIDTH, A4_HEIGHT, MARGIN = 11906, 16838, 1134  # twips; 2 cm = 1134
BODY = 24  # half-points
NS = nsdecls("w")
BORDER = "BFBFBF"
HEADING_SIZES = {1: 36, 2: 28, 3: 26}
SHADED_HEADING = 2


def _fonts() -> str:
    return (
        f'<w:rFonts w:ascii="{LATIN_FONT}" w:hAnsi="{LATIN_FONT}" w:eastAsia="{LATIN_FONT}" '
        f'w:cs="{ARABIC_FONT}"/>'
    )


def _rpr(*, size: int = BODY, bold: bool = False, color: str | None = None) -> str:
    return (
        f"<w:rPr {NS}>{_fonts()}"
        + ("<w:b/><w:bCs/>" if bold else "")
        + (f'<w:color w:val="{color}"/>' if color else "")
        + f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
    )


def _ppr(  # noqa: PLR0913 -- a flat bag of optional paragraph properties
    *,
    rtl: bool,
    keep_next: bool = False,
    keep_lines: bool = False,
    border: str = "",
    fill: str | None = None,
    before: int = 0,
    after: int = 80,
    line: int | None = None,
    align: str | None = None,
) -> str:
    spacing = f'<w:spacing w:before="{before}" w:after="{after}"'
    if line:
        spacing += f' w:line="{line}" w:lineRule="exact"'
    return (
        f"<w:pPr {NS}>"
        + ("<w:keepNext/>" if keep_next else "")
        + ("<w:keepLines/>" if keep_lines else "")
        + (f"<w:pBdr>{border}</w:pBdr>" if border else "")
        + (f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else "")
        + ("<w:bidi/>" if rtl else "")
        + f"{spacing}/>"
        + (f'<w:jc w:val="{align}"/>' if align else "")
        + "</w:pPr>"
    )


def _box(color: str = BORDER) -> str:
    return "".join(
        f'<w:{side} w:val="single" w:sz="6" w:space="4" w:color="{color}"/>'
        for side in ("top", "left", "bottom", "right")
    )


def _replace(style: BaseStyle, ppr: str | None, rpr: str | None) -> None:
    element = style.element
    for tag, xml in (("w:pPr", ppr), ("w:rPr", rpr)):
        old = element.find(qn(tag))
        if old is not None:
            element.remove(old)
        if xml:
            element.append(parse_xml(xml))


def _table_style(style_id: str, name: str, *, bordered: bool) -> str:
    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="{BORDER}"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    first_row = (
        '<w:tblStylePr w:type="firstRow"><w:rPr><w:b/><w:bCs/></w:rPr>'
        '<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="E8E8E8"/></w:tcPr></w:tblStylePr>'
    )
    return (
        f'<w:style {NS} w:type="table" w:customStyle="1" w:styleId="{style_id}">'
        f'<w:name w:val="{name}"/><w:basedOn w:val="TableNormal"/><w:qFormat/>'
        '<w:tblPr><w:tblStyleRowBandSize w:val="1"/><w:tblStyleColBandSize w:val="1"/>'
        + (f"<w:tblBorders>{borders}</w:tblBorders>" if bordered else "")
        + '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
        '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
        "</w:tblPr>" + (first_row if bordered else "") + "</w:style>"
    )


def _default_reference() -> bytes:
    result = subprocess.run(  # noqa: S603 -- the bundled pandoc binary, fixed arguments
        [pypandoc.get_pandoc_path(), "--print-default-data-file", "reference.docx"],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _add_footer_page_number(document: DocumentType, *, rtl: bool) -> None:
    footer = document.sections[0].footer
    footer.is_linked_to_previous = False
    paragraph: Paragraph = footer.paragraphs[0]
    paragraph._p.append(parse_xml(_ppr(rtl=rtl, align="center", after=0)))
    paragraph._p.append(
        parse_xml(
            f'<w:fldSimple {NS} w:instr=" PAGE ">'
            f"<w:r>{_rpr(size=20)}<w:t>1</w:t></w:r></w:fldSimple>"
        )
    )


def build(language: str) -> bytes:
    """The reference document for ``ar`` (RTL) or any other language (LTR)."""
    rtl = language == "ar"
    document = Document(BytesIO(_default_reference()))
    styles = document.styles
    body = _ppr(rtl=rtl)
    for name in ("Normal", "Body Text", "First Paragraph"):
        _replace(styles[name], body, _rpr() if name == "Normal" else None)
    _replace(styles["Compact"], _ppr(rtl=rtl, after=20), None)
    for level in (1, 2, 3):
        size = HEADING_SIZES[level]
        fill = "E8E8E8" if level == SHADED_HEADING else None
        _replace(
            styles[f"Heading {level}"],
            _ppr(rtl=rtl, keep_next=True, fill=fill, before=160, after=80),
            _rpr(size=size, bold=True),
        )
    _replace(styles["Block Text"], _ppr(rtl=rtl, border=_box(), after=80), None)

    def paragraph(name: str, ppr: str, rpr: str | None = None) -> None:
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = styles["Normal"]
        style.quick_style = True
        _replace(style, ppr, rpr)

    paragraph("ExamSchool", _ppr(rtl=rtl, after=40, align="center"), _rpr(size=28, bold=True))
    paragraph("ExamTitle", _ppr(rtl=rtl, after=80, align="center"), _rpr(size=32, bold=True))
    paragraph("Instructions", _ppr(rtl=rtl, border=_box(), before=80, after=80))
    paragraph("SectionNote", _ppr(rtl=rtl, after=80))
    paragraph("Stimulus", _ppr(rtl=rtl, border=_box(), fill="F7F7F7", before=60, after=60))
    paragraph("StimulusIntro", _ppr(rtl=rtl, keep_next=True, after=40), _rpr(bold=True))
    paragraph("Question", _ppr(rtl=rtl, keep_lines=True, before=100, after=40))
    # Word merges the borders of adjacent paragraphs, so `between` draws the line under each one.
    answer_line = "".join(
        f'<w:{side} w:val="dotted" w:sz="6" w:space="1" w:color="808080"/>'
        for side in ("bottom", "between")
    )
    paragraph("AnswerLine", _ppr(rtl=rtl, border=answer_line, before=0, after=0, line=480))
    points = styles.add_style("Points", WD_STYLE_TYPE.CHARACTER)
    _replace(points, None, _rpr(size=18, color="595959"))
    for xml in (
        _table_style("Table", "Table", bordered=True),
        _table_style("PlainTable", "PlainTable", bordered=False),
    ):
        element = parse_xml(xml)
        old = [
            s
            for s in styles.element.findall(qn("w:style"))
            if s.get(qn("w:styleId")) == element.get(qn("w:styleId"))
        ]
        for stale in old:
            styles.element.remove(stale)
        styles.element.append(element)
    if styles.element.find(f".//{qn('w:style')}[@{qn('w:styleId')}='TableNormal']") is None:
        styles.element.append(
            parse_xml(
                f'<w:style {NS} w:type="table" w:default="1" w:styleId="TableNormal">'
                '<w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/>'
                '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar>'
                '<w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
                '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
                "</w:tblCellMar></w:tblPr></w:style>"
            )
        )
    section = document.sections[0]
    section.page_width, section.page_height = Twips(A4_WIDTH), Twips(A4_HEIGHT)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Twips(MARGIN))
    section.footer_distance = Twips(567)
    _add_footer_page_number(document, rtl=rtl)
    out = BytesIO()
    document.save(out)
    return out.getvalue()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for language, name in (("ar", "rtl"), ("en", "ltr")):
        (OUT_DIR / f"reference-{name}.docx").write_bytes(build(language))


if __name__ == "__main__":
    main()
