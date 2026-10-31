"""Generate the synthetic 2-page Arabic e2e workbook and the matching scripted fake-LLM file.

Run from the repo root (fontTools and brotli are only needed here, to turn the vendored
woff2 Noto Naskh files into TTFs that MuPDF can load):

    uv run --directory backend --with fonttools --with brotli python ../scripts/e2e/make_fixture.py

Outputs `scripts/e2e/workbook.pdf` and `scripts/e2e/fake_llm.json`. Both are synthetic and committed.
The boxes in the script are computed from the very rectangles the PDF is drawn at.
"""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "backend/src/qbank/export/vendor/fonts"
OUT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 595.0, 842.0
LABELS = ["أ", "ب", "ج", "د"]
CSS = (
    "@font-face{font-family:nkl;src:url(latin.ttf);}"
    "@font-face{font-family:nka;src:url(arabic.ttf);}"
    "body{font-family:nkl,nka;font-size:13pt;direction:rtl;line-height:1.5}"
    "h1{font-size:20pt;text-align:center}.stem{font-weight:normal}"
)


@dataclass
class Mcq:
    number: str
    stem: str
    choices: list[str]
    correct: int
    rect: pymupdf.Rect
    figure: pymupdf.Rect | None = None
    stimulus_ref: str | None = None
    difficulty: int = 2
    tags: tuple[str, ...] = ()


PAGE1 = [
    Mcq(
        "1",
        "ما وظيفة الميتوكوندريا في الخَلِيَّةِ؟",
        ["إنتاج الطاقة", "تخزين الماء", "بناء الجدار الخلوي", "نقل الأكسجين"],
        0,
        pymupdf.Rect(40, 100, 555, 210),
        difficulty=1,
        tags=("خلية",),
    ),
    Mcq(
        "2",
        "أي العضيات التالية تقوم بعملية البناء الضوئي؟",
        ["النواة", "البلاستيدات الخضراء", "الريبوسومات", "الجهاز الغولجي"],
        1,
        pymupdf.Rect(40, 220, 555, 330),
        tags=("عضيات",),
    ),
    Mcq(
        "3",
        "ما الجزيء الذي يحمل المعلومات الوراثية؟",
        ["البروتين", "الدهون", "الحمض النووي", "النشا"],
        2,
        pymupdf.Rect(40, 340, 555, 450),
        difficulty=3,
        tags=("وراثة",),
    ),
    Mcq(
        "4",
        "يمثل الشكل المقابل خلية نباتية، فما اسم الجزء المشار إليه؟",
        ["الفجوة العصارية", "النواة", "الغشاء", "السيتوبلازم"],
        0,
        pymupdf.Rect(40, 460, 555, 640),
        figure=pymupdf.Rect(60, 480, 220, 620),
        difficulty=2,
        tags=("شكل",),
    ),
]
PAGE2 = [
    Mcq(
        "5",
        "ما الناتج النهائي لعملية التنفس الخلوي الهوائي؟",
        ["الإيثانول", "حمض اللاكتيك", "الماء وثاني أكسيد الكربون", "الجلوكوز"],
        2,
        pymupdf.Rect(40, 40, 555, 150),
        difficulty=3,
        tags=("تنفس",),
    ),
    Mcq(
        "6",
        "أي مما يلي ينتقل عبر الغشاء بالانتشار البسيط؟",
        ["الأكسجين", "البروتينات", "النشا", "الحمض النووي"],
        0,
        pymupdf.Rect(40, 160, 555, 270),
        tags=("غشاء",),
    ),
]
PASSAGE_RECT = pymupdf.Rect(40, 285, 555, 410)
PASSAGE = (
    "تتكاثر البكتيريا بالانقسام الثنائي، إذ تنقسم الخلية الواحدة إلى خليتين متماثلتين "
    "في ظروف مناسبة من الحرارة والغذاء، وقد يتكرر ذلك كل عشرين دقيقة."
)
PAGE2_PASSAGE_QUESTIONS = [
    Mcq(
        "7",
        "ما نوع التكاثر الموصوف في القطعة؟",
        ["جنسي", "انقسام ثنائي", "تبرعم", "تجدد"],
        1,
        pymupdf.Rect(40, 420, 555, 530),
        stimulus_ref="S1",
        tags=("تكاثر",),
    ),
    Mcq(
        "8",
        "ما العامل الذي يسرّع تكاثر البكتيريا بحسب القطعة؟",
        ["البرودة الشديدة", "الجفاف", "الحرارة والغذاء المناسبان", "الضوء فقط"],
        2,
        pymupdf.Rect(40, 540, 555, 650),
        stimulus_ref="S1",
        difficulty=3,
        tags=("تكاثر",),
    ),
]
TITLE_RECT = pymupdf.Rect(40, 40, 555, 90)
TITLE = "الفصل الأول: الخلية"


def box(rect: pymupdf.Rect) -> list[int]:
    """Gemini convention: [ymin, xmin, ymax, xmax] on a 0-1000 scale."""
    return [
        round(rect.y0 / HEIGHT * 1000),
        round(rect.x0 / WIDTH * 1000),
        round(rect.y1 / HEIGHT * 1000),
        round(rect.x1 / WIDTH * 1000),
    ]


def question_html(q: Mcq) -> str:
    lines = [f'<p class="stem"><b>{q.number}.</b> {q.stem}</p>']
    lines += [f"<p>{LABELS[i]}) {choice}</p>" for i, choice in enumerate(q.choices)]
    return "".join(lines)


def draw_question(page: pymupdf.Page, archive: pymupdf.Archive, q: Mcq) -> None:
    rect = pymupdf.Rect(q.rect)
    if q.figure is not None:
        # Keep the text clear of the figure, which sits at the left of the block.
        rect = pymupdf.Rect(q.figure.x1 + 15, q.rect.y0, q.rect.x1, q.rect.y1)
        page.draw_rect(q.figure, color=(0.1, 0.35, 0.2), fill=(0.8, 0.93, 0.82), width=2)
        page.draw_circle(q.figure.tl + (q.figure.br - q.figure.tl) * 0.5, 30, color=(0.1, 0.35, 0.2))
    page.insert_htmlbox(rect, question_html(q), css=CSS, archive=archive)


def question_json(q: Mcq) -> dict[str, object]:
    return {
        "number_label": q.number,
        "type": "mcq_single",
        "stem": q.stem,
        "choices": [{"label": LABELS[i], "content": c} for i, c in enumerate(q.choices)],
        "answer": {"labels": [LABELS[q.correct]], "text": None},
        "stimulus_ref": q.stimulus_ref,
        "figures": [{"box_2d": box(q.figure), "kind": "diagram"}] if q.figure else [],
        "box_2d": box(q.rect),
        "continues_from_previous": False,
        "continues_on_next": False,
        "confidence": 0.95,
    }


def page_json(
    kind: str, questions: list[Mcq], *, headings: list[object], stimuli: list[object]
) -> dict[str, object]:
    return {
        "page_kind": kind,
        "headings": headings,
        "stimuli": stimuli,
        "questions": [question_json(q) for q in questions],
        "answer_key_entries": [],
        "page_confidence": 0.95,
        "notes": "",
    }


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for script in ("arabic", "latin"):
            font = TTFont(FONTS / f"noto-naskh-arabic-{script}-400-normal.woff2")
            font.flavor = None
            font.save(Path(tmp) / f"{script}.ttf")
        archive = pymupdf.Archive(tmp)
        doc = pymupdf.open()
        page1 = doc.new_page(width=WIDTH, height=HEIGHT)
        page1.insert_htmlbox(TITLE_RECT, f"<h1>{TITLE}</h1>", css=CSS, archive=archive)
        for q in PAGE1:
            draw_question(page1, archive, q)
        page2 = doc.new_page(width=WIDTH, height=HEIGHT)
        for q in PAGE2:
            draw_question(page2, archive, q)
        page2.draw_rect(PASSAGE_RECT, color=(0.3, 0.3, 0.3), width=1)
        page2.insert_htmlbox(
            PASSAGE_RECT + (8, 4, -8, -4), f"<p>{PASSAGE}</p>", css=CSS, archive=archive
        )
        for q in PAGE2_PASSAGE_QUESTIONS:
            draw_question(page2, archive, q)
        doc.set_metadata({"title": "Qbank e2e synthetic workbook", "author": "Qbank"})
        doc.save(OUT / "workbook.pdf", garbage=4, deflate=True)

    all_questions = [*PAGE1, *PAGE2, *PAGE2_PASSAGE_QUESTIONS]
    heading = {"level": "chapter", "text": TITLE, "box_2d": box(TITLE_RECT)}
    stimulus = {
        "ref": "S1",
        "kind": "passage",
        "intro": None,
        "content": PASSAGE,
        "box_2d": box(PASSAGE_RECT),
        "continues_from_previous": False,
        "continues_on_next": False,
    }
    script = {
        "extract": [
            page_json("questions", PAGE1, headings=[heading], stimuli=[]),
            page_json(
                "questions",
                [*PAGE2, *PAGE2_PASSAGE_QUESTIONS],
                headings=[],
                stimuli=[stimulus],
            ),
        ],
        "verify": [{"discrepancies": []}],
        "classify": [
            {
                "items": [
                    {
                        "id": q.number,
                        "difficulty": q.difficulty,
                        "difficulty_reason": "سؤال مباشر من المنهج",
                        "tags": list(q.tags),
                    }
                    for q in all_questions
                ]
            }
        ],
        "compose": [
            {
                "title": "اختبار الأحياء المقترح",
                "duration_minutes": 45,
                "sections": [
                    {
                        "title": "القسم الأول",
                        "rows": [{"count": 2, "types": ["mcq_single"], "points": 2}],
                    }
                ],
                "notes": "",
            },
            {
                "rows": [{"refs": ["c1", "c2"]}],
                "rationale": "اختيار سؤالين متوازنين في الصعوبة من بنك الأسئلة.",
            },
        ],
    }
    (OUT / "fake_llm.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
