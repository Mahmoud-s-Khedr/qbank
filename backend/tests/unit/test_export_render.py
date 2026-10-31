import re
from pathlib import Path
from uuid import uuid4

import pytest

from qbank.export.render import render_answer_key, render_bubble_sheet, render_exam
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
    choices_per_row,
    format_number,
)
from qbank.schemas.exams import AnswerKey, AnswerKeyEntry, ExamLayout

ANSWER_LINES = 3
TOTAL_BUBBLES = 5


def mcq(number: int, *contents: str, points: float = 1) -> QuestionView:
    letters = "أبجد"
    return QuestionView(
        number,
        "mcq_single",
        f"stem {number}",
        points,
        [ChoiceView(letters[i], c) for i, c in enumerate(contents)],
    )


def view(
    groups: list[GroupView],
    *,
    language: str = "ar",
    layout: ExamLayout | None = None,
    header: HeaderView | None = None,
) -> ExamView:
    return ExamView(
        language=language,
        version_label="ب" if language == "ar" else "B",
        header=header or HeaderView(school_name="School", exam_title="Midterm", subject="Math"),
        layout=layout or ExamLayout(),
        sections=[SectionView("Part one", "Do all", groups)],
    )


def test_rtl_and_ltr_documents() -> None:
    ar = render_exam(view([GroupView([mcq(1, "a", "b")])]))
    en = render_exam(view([GroupView([mcq(1, "a", "b")])], language="en"))
    assert '<html dir="rtl" lang="ar">' in ar
    assert '<html dir="ltr" lang="en">' in en
    assert "Student name" in en
    assert "اسم الطالب" in ar


def test_header_fields_and_totals() -> None:
    header = HeaderView(
        school_name="مدرسة النور",
        exam_title="اختبار",
        subject="رياضيات",
        grade="3",
        date="2026-10-31",
        duration_minutes=45,
        instructions="اقرأ جيدا",
    )
    html = render_exam(
        view([GroupView([mcq(1, "a", points=2), mcq(2, "b", points=0.5)])], header=header)
    )
    for text in (
        "مدرسة النور",
        "اختبار",
        "رياضيات",
        "\u0662\u0660\u0662\u0666-\u0661\u0660-\u0663\u0661",
        "\u0664\u0665",
        "اقرأ جيدا",
    ):
        assert text in html
    assert "\u0662\u066b\u0665" in html  # total marks


def test_arabic_digits_only_when_configured() -> None:
    questions = [GroupView([mcq(12, "x", points=3)])]
    arabic = render_exam(view(questions, layout=ExamLayout(digits="arabic")))
    western = render_exam(view(questions, layout=ExamLayout(digits="western")))
    assert "١٢-" in arabic
    assert "12-" in western
    assert "١٢-" not in western
    # Question content is never converted.
    content = render_exam(view([GroupView([QuestionView(1, "essay", "اكتب 123", 1)])]))
    assert "اكتب 123" in content


def test_stimulus_printed_once_before_its_group() -> None:
    group = GroupView(
        [mcq(1, "a"), mcq(2, "b"), mcq(3, "c")], StimulusView("passage", "PASSAGE-TEXT")
    )
    html = render_exam(view([group]))
    assert html.count("PASSAGE-TEXT") == 1
    assert html.index("PASSAGE-TEXT") < html.index("stem 1")
    assert "اقرأ النص" in html


def test_choices_in_given_order_with_version_lettering() -> None:
    html = render_exam(view([GroupView([mcq(1, "zz-third", "zz-first", "zz-second")])]))
    order = [html.index(w) for w in ("zz-third", "zz-first", "zz-second")]
    assert order == sorted(order)
    assert '<span class="lbl">أ</span>' in html
    assert '<span class="lbl">ج</span>' in html


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        (["a" * 18, "b"], 4),
        (["a" * 19, "b"], 2),
        (["a" * 40], 2),
        (["a" * 41], 1),
        ([], 4),
    ],
)
def test_auto_choice_layout_thresholds(contents: list[str], expected: int) -> None:
    assert auto_choices_per_row(contents) == expected
    assert choices_per_row("auto", contents) == expected


def test_explicit_choices_per_row_overrides_auto() -> None:
    assert choices_per_row(1, ["a"]) == 1
    html = render_exam(view([GroupView([mcq(1, "a", "b")])], layout=ExamLayout(choices_per_row=2)))
    assert "repeat(2," in html
    auto = render_exam(view([GroupView([mcq(1, "a", "b")])]))
    assert "repeat(4," in auto


def test_layout_options_columns_font_and_lines() -> None:
    essay = QuestionView(1, "essay", "explain", 5)
    html = render_exam(
        view(
            [GroupView([essay])],
            layout=ExamLayout(columns=2, font_size_pt=14, answer_space_lines=3),
        )
    )
    assert "cols-2" in html
    assert "font-size: 14pt" in html
    assert html.count("<div></div>") == ANSWER_LINES
    none = render_exam(view([GroupView([essay])], layout=ExamLayout(answer_space_lines=0)))
    assert 'class="lines"' not in none
    assert 'class="lines"' not in render_exam(view([GroupView([mcq(1, "a")])]))


def test_points_shown_per_question() -> None:
    html = render_exam(view([GroupView([mcq(1, "a", points=1), mcq(2, "b", points=2)])]))
    assert "(\u0661 درجة)" in html
    assert "(\u0662 درجات)" in html


def test_content_html_is_escaped() -> None:
    q = QuestionView(1, "essay", "<script>x</script>", 1)
    html = render_exam(view([GroupView([q])], header=HeaderView(exam_title="<b>t</b>")))
    assert "<script>x" not in html
    assert "&lt;b&gt;t" in html


def test_bubble_sheet_only_for_all_mcq() -> None:
    ok = view([GroupView([mcq(1, "a", "b"), mcq(2, "a", "b", "c")])])
    html = render_bubble_sheet(ok)
    assert html.count('class="bubble"') == TOTAL_BUBBLES
    assert "ب" in html  # version label
    mixed = view([GroupView([mcq(1, "a"), QuestionView(2, "essay", "e", 1)])])
    assert not mixed.all_mcq
    with pytest.raises(ValueError, match="multiple-choice"):
        render_bubble_sheet(mixed)


def test_answer_key_table() -> None:
    entries = [
        AnswerKeyEntry(
            number=1,
            question_id=uuid4(),
            type="mcq_single",
            correct=["ج"],
            answer_text=None,
            points=1,
        ),
        AnswerKeyEntry(
            number=2,
            question_id=uuid4(),
            type="mcq_multi",
            correct=["أ", "ب"],
            answer_text=None,
            points=2,
        ),
        AnswerKeyEntry(
            number=3,
            question_id=uuid4(),
            type="essay",
            correct=None,
            answer_text="because",
            points=3,
        ),
        AnswerKeyEntry(
            number=4,
            question_id=uuid4(),
            type="mcq_single",
            correct=None,
            answer_text=None,
            points=1,
        ),
    ]
    base = view([GroupView([mcq(1, "a"), mcq(2, "b"), mcq(3, "c"), mcq(4, "d")])])
    html = render_answer_key(base.with_key(AnswerKey(label="ب", items=entries, warnings=[])))
    assert "ج" in html
    assert "أ، ب" in html
    assert "because" in html
    assert "—" in html
    assert "\u0667" in html  # the key rows add up to 7 (1 + 2 + 3 + 1)
    with pytest.raises(ValueError, match="answer key"):
        render_answer_key(base)


def test_digit_helpers() -> None:
    assert arabic_digits("2026-10-31") == "\u0662\u0660\u0662\u0666-\u0661\u0660-\u0663\u0661"
    assert arabic_digits("2.5") == "\u0662\u066b\u0665"
    assert arabic_digits("end.") == "end."
    assert format_number(2.0) == "2"
    assert format_number(0.5) == "0.5"


def test_templates_use_logical_css_properties_only() -> None:
    root = Path(__file__).parents[2] / "src" / "qbank" / "export" / "templates"
    physical = re.compile(r"(margin|padding|border)-(left|right)|(?<![-\w])(left|right)\s*:")
    for template in root.glob("*.j2"):
        text = re.sub(r"<script>.*?</script>", "", template.read_text(encoding="utf-8"), flags=re.S)
        assert not physical.search(text.replace("text-align: left", "")), template.name
