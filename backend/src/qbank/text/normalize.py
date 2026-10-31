"""Arabic and QMD text normalization for search and deduplication."""

import hashlib
import re
from collections.abc import Mapping, Sequence

# Tashkeel (U+064B..U+065F, U+0670, U+06D6..U+06ED) and tatweel (U+0640).
_TASHKEEL_TATWEEL_RE = re.compile(r"[\u0640\u064B-\u065F\u0670\u06D6-\u06ED]")

# QMD figure references: ![caption](asset:...)
_ASSET_REF_RE = re.compile(r"!\[[^\]]*\]\(asset:[^)]*\)", re.IGNORECASE)

# Markdown and QMD formatting delimiters ($ kept as inner TeX content).
_MARKDOWN_PUNCT_RE = re.compile(r"[#$*_~`>|!\[\]()]")

_WHITESPACE_RE = re.compile(r"\s+")

_ARABIC_AND_DIGIT_MAP = str.maketrans(
    {
        # Unify alef variants -> bare alef (U+0627)
        "\u0623": "\u0627",
        "\u0625": "\u0627",
        "\u0622": "\u0627",
        "\u0671": "\u0627",
        # Alef maqsura -> yeh (U+064A)
        "\u0649": "\u064a",
        # Teh marbuta -> heh (U+0647)
        "\u0629": "\u0647",
        # Waw with hamza -> waw (U+0648)
        "\u0624": "\u0648",
        # Yeh with hamza -> yeh (U+064A)
        "\u0626": "\u064a",
        # Arabic-Indic digits (U+0660..U+0669) -> ASCII (0..9)
        "\u0660": "0",
        "\u0661": "1",
        "\u0662": "2",
        "\u0663": "3",
        "\u0664": "4",
        "\u0665": "5",
        "\u0666": "6",
        "\u0667": "7",
        "\u0668": "8",
        "\u0669": "9",
        # Persian / Extended Arabic-Indic digits (U+06F0..U+06F9) -> ASCII (0..9)
        "\u06f0": "0",
        "\u06f1": "1",
        "\u06f2": "2",
        "\u06f3": "3",
        "\u06f4": "4",
        "\u06f5": "5",
        "\u06f6": "6",
        "\u06f7": "7",
        "\u06f8": "8",
        "\u06f9": "9",
        # Avoid U+0130 expanding to two code points on .lower()
        "\u0130": "i",
    }
)


def normalize_ar(text: str) -> str:
    """Normalize Arabic/mixed QMD text for deduplication and fuzzy matching.

    - Strips tashkeel (U+064B-U+0652, U+0670) and tatweel (U+0640)
    - Unifies alef forms (U+0623, U+0625, U+0622, U+0671 -> U+0627),
      alef maqsura (U+0649 -> U+064A), teh marbuta (U+0629 -> U+0647),
      hamza on waw (U+0624 -> U+0648), hamza on yeh (U+0626 -> U+064A)
    - Maps Arabic-Indic and Persian digits to ASCII
    - Lowercases Latin characters
    - Drops QMD syntax ($...$ kept as its TeX content, ![...](asset:...) removed,
      Markdown punctuation stripped)
    - Collapses whitespace
    """
    cleaned = _TASHKEEL_TATWEEL_RE.sub("", text)
    cleaned = _ASSET_REF_RE.sub(" ", cleaned)
    cleaned = _MARKDOWN_PUNCT_RE.sub(" ", cleaned)
    cleaned = cleaned.translate(_ARABIC_AND_DIGIT_MAP).lower()
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def question_normalized_text(
    stem: str,
    choices: Sequence[Mapping[str, object]],
    stimulus_intro: str | None = None,
) -> str:
    """Build normalized text from stem + choice contents + stimulus intro."""
    parts: list[str] = [stem]
    for choice in choices:
        content = choice.get("content")
        if isinstance(content, str) and content:
            parts.append(content)
    if stimulus_intro:
        parts.append(stimulus_intro)
    return normalize_ar(" ".join(parts))


def content_hash(normalized_text: str) -> str:
    """Compute SHA-256 hex digest of normalized question text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
