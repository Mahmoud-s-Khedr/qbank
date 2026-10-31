"""Exam views to self-contained HTML documents (Jinja2, autoescape on)."""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from qbank.export.qmd import AssetResolver, render_qmd
from qbank.export.view import (
    ExamView,
    choices_per_row,
    digits_formatter,
)

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor"
FONT_FACES = (
    ("arabic", 400, "U+0600-06FF,U+0750-077F,U+0870-08FF,U+FB50-FDFF,U+FE70-FEFF,U+200C-200F"),
    ("arabic", 700, "U+0600-06FF,U+0750-077F,U+0870-08FF,U+FB50-FDFF,U+FE70-FEFF,U+200C-200F"),
    ("latin", 400, "U+0000-05FF,U+2000-206F,U+20AC,U+2122,U+2212"),
    ("latin", 700, "U+0000-05FF,U+2000-206F,U+20AC,U+2122,U+2212"),
)

STRINGS: dict[str, dict[str, str]] = {
    "ar": {
        "student_name": "اسم الطالب",
        "student_number": "رقم الجلوس",
        "class": "الصف / الفصل",
        "subject": "المادة",
        "grade": "الصف",
        "date": "التاريخ",
        "duration": "المدة",
        "minutes": "دقيقة",
        "total": "الدرجة الكلية",
        "instructions": "تعليمات",
        "version": "النموذج",
        "mark": "درجة",
        "marks": "درجات",
        "intro": "اقرأ النص ثم أجب عن الأسئلة التالية",
        "true": "صح",
        "false": "خطأ",
        "key_title": "نموذج الإجابة",
        "number": "رقم السؤال",
        "answer": "الإجابة الصحيحة",
        "points": "الدرجة",
        "bubble_title": "ورقة الإجابة",
        "bubble_hint": "ظلل الدائرة المناسبة بالكامل بقلم حبر داكن",
    },
    "en": {
        "student_name": "Student name",
        "student_number": "Student number",
        "class": "Class",
        "subject": "Subject",
        "grade": "Grade",
        "date": "Date",
        "duration": "Duration",
        "minutes": "min",
        "total": "Total marks",
        "instructions": "Instructions",
        "version": "Version",
        "mark": "mark",
        "marks": "marks",
        "intro": "Read the text, then answer the questions that follow",
        "true": "True",
        "false": "False",
        "key_title": "Answer key",
        "number": "No.",
        "answer": "Correct answer",
        "points": "Points",
        "bubble_title": "Answer sheet",
        "bubble_hint": "Fill the matching circle completely with a dark pen",
    },
}


def _font_uri(subset: str, weight: int) -> str:
    return (VENDOR / "fonts" / f"noto-naskh-arabic-{subset}-{weight}-normal.woff2").as_uri()


@lru_cache
def _css_assets() -> dict[str, str]:
    """Vendored CSS with font URLs rewritten to absolute ``file://`` paths."""
    katex = (VENDOR / "katex" / "katex.min.css").read_text(encoding="utf-8")
    katex = katex.replace("url(fonts/", f"url({(VENDOR / 'katex' / 'fonts').as_uri()}/")
    faces = "".join(
        "@font-face{font-family:'Noto Naskh Arabic';font-style:normal;font-display:block;"
        f"font-weight:{weight};unicode-range:{ranges};"
        f"src:url({_font_uri(subset, weight)}) format('woff2')}}"
        for subset, weight, ranges in FONT_FACES
    )
    return {"katex_css": katex, "font_css": faces}


@lru_cache
def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "j2"], default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(_css_assets())
    env.globals["vendor"] = {
        "katex": (VENDOR / "katex" / "katex.min.js").as_uri(),
        "auto_render": (VENDOR / "katex" / "contrib" / "auto-render.min.js").as_uri(),
        "mhchem": (VENDOR / "katex" / "contrib" / "mhchem.min.js").as_uri(),
    }
    env.globals["choices_per_row"] = choices_per_row
    return env


def _context(view: ExamView, assets: AssetResolver | None) -> dict[str, object]:
    digits = digits_formatter(view.language, view.layout.digits)

    def qmd(source: str) -> Markup:
        return Markup(render_qmd(source, assets))  # noqa: S704 -- QMD output is escaped HTML

    def qmd_inline(source: str) -> Markup:
        return Markup(render_qmd(source, assets, inline=True))  # noqa: S704 -- as above

    rtl = view.language == "ar"
    return {
        "view": view,
        "t": STRINGS[view.language],
        "dir": "rtl" if rtl else "ltr",
        "lang": view.language,
        "d": digits,
        "qmd": qmd,
        "qmd_inline": qmd_inline,
        "layout": view.layout,
    }


def _render(name: str, view: ExamView, assets: AssetResolver | None) -> str:
    return _environment().get_template(name).render(**_context(view, assets))


def render_exam(view: ExamView, assets: AssetResolver | None = None) -> str:
    return _render("exam.html.j2", view, assets)


def render_answer_key(view: ExamView, assets: AssetResolver | None = None) -> str:
    if view.key is None:
        raise ValueError("answer key missing")
    return _render("answer_key.html.j2", view, assets)


def render_bubble_sheet(view: ExamView) -> str:
    if not view.all_mcq:
        raise ValueError("bubble sheets need an exam made only of multiple-choice questions")
    return _render("bubble_sheet.html.j2", view, None)
