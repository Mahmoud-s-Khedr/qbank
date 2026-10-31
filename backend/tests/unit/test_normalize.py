"""Unit and property tests for Arabic and QMD normalization."""

from hypothesis import given, settings
from hypothesis import strategies as st

from qbank.text.normalize import content_hash, normalize_ar, question_normalized_text

SHA256_HEX_LEN = 64


def _count_letters(text: str) -> int:
    return sum(1 for ch in text if ch.isalpha())


def test_normalize_ar_tashkeel_and_tatweel() -> None:
    raw = "السُّؤَالُ الأَوَّلُ: كَتَـبَ الطَّالِبُ الدَّرْسَٰ"
    assert normalize_ar(raw) == "السوال الاول: كتب الطالب الدرس"


def test_normalize_ar_character_unification() -> None:
    raw = "أحمد إبراهيم آمنة ٱستغفر على مدرسة سؤال بئر"
    assert normalize_ar(raw) == "احمد ابراهيم امنه استغفر علي مدرسه سوال بير"


def test_normalize_ar_digits_and_latin() -> None:
    raw = "Question ١٢٣ and ۴۵۶ with ABC xyz"
    assert normalize_ar(raw) == "question 123 and 456 with abc xyz"


def test_normalize_ar_qmd_syntax_stripped() -> None:
    raw = (
        "# **السؤال** الأول: احسب $\\frac{x^2 + 1}{2}$ في الشكل "
        "![الشكل المقابل](asset:123e4567-e89b-12d3-a456-426614174000) "
        "ثم أكمل ____ في الجدول | أ | ب |"
    )
    normalized = normalize_ar(raw)
    assert "asset:" not in normalized
    assert "123e4567" not in normalized
    assert "\\frac{x^2 + 1}{2}" in normalized
    assert "$" not in normalized
    assert "**" not in normalized
    assert "____" not in normalized


def test_question_normalized_text_and_hash() -> None:
    norm = question_normalized_text(
        stem="ما عاصمة مِصْر؟",
        choices=[{"label": "أ", "content": "القاهرة"}, {"label": "ب", "content": "الإسكندرية"}],
        stimulus_intro="اقرأ الفقرة التالية:",
    )
    assert norm == "ما عاصمه مصر؟ القاهره الاسكندريه اقرا الفقره التاليه:"
    digest = content_hash(norm)
    assert len(digest) == SHA256_HEX_LEN
    assert digest == content_hash(norm)


@settings(max_examples=200)
@given(st.text())
def test_normalize_ar_is_idempotent(text: str) -> None:
    once = normalize_ar(text)
    twice = normalize_ar(once)
    assert twice == once


@settings(max_examples=200)
@given(st.text())
def test_normalize_ar_never_longer_in_letters(text: str) -> None:
    normalized = normalize_ar(text)
    assert _count_letters(normalized) <= _count_letters(text)


_AR_QMD_ALPHABET = (
    "ابتثجحخدذرزسشصضطظعغفقكلمنهويأإآٱىةؤئ"
    "\u0640\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670"
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    " $![]()*_~`#>|-:\\/{}^+=،؟.\n\t"
)


@settings(max_examples=200)
@given(st.text(alphabet=_AR_QMD_ALPHABET, min_size=0, max_size=120))
def test_normalize_ar_mixed_arabic_qmd_properties(text: str) -> None:
    once = normalize_ar(text)
    assert normalize_ar(once) == once
    assert _count_letters(once) <= _count_letters(text)
