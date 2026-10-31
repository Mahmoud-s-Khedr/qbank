"""Seeded exam versions: item order, choice permutations, display labels and answer keys."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

ARABIC_LETTERS = ["أ", "ب", "ج", "د", "هـ", "و", "ز", "ح", "ط", "ي"]
LATIN_LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
CHOICE_TYPES = frozenset({"mcq_single", "mcq_multi"})


def alphabet(language: str) -> list[str]:
    return ARABIC_LETTERS if language == "ar" else LATIN_LETTERS


def display_label(language: str, index: int) -> str:
    letters = alphabet(language)
    return letters[index] if index < len(letters) else str(index + 1)


@dataclass(frozen=True)
class ChoiceSpec:
    pinned: bool = False


@dataclass(frozen=True)
class ItemSpec:
    item_id: UUID
    question_id: UUID
    type: str
    points: float
    stimulus_id: UUID | None
    choices: Sequence[ChoiceSpec]


def permute_choices(choices: Sequence[ChoiceSpec], rng: random.Random) -> list[int]:
    """Display order as source indices. Pinned choices keep their slot; the rest are shuffled."""
    free = [i for i, c in enumerate(choices) if not c.pinned]
    shuffled = free[:]
    rng.shuffle(shuffled)
    order = list(range(len(choices)))
    for slot, source in zip(free, shuffled, strict=True):
        order[slot] = source
    return order


def _units(items: Sequence[ItemSpec]) -> list[list[ItemSpec]]:
    units: list[list[ItemSpec]] = []
    for item in items:
        if units and item.stimulus_id is not None and units[-1][0].stimulus_id == item.stimulus_id:
            units[-1].append(item)
        else:
            units.append([item])
    return units


def build_layout(
    sections: Sequence[tuple[UUID, Sequence[ItemSpec]]],
    *,
    seed: int,
    shuffle_questions: bool = True,
    shuffle_choices: bool = True,
) -> dict[str, object]:
    """One version's layout. Numbering is continuous across sections; groups move as a unit."""
    rng = random.Random(seed)  # noqa: S311 -- shuffling, not cryptography
    number = 0
    out_sections: list[dict[str, object]] = []
    for section_id, items in sections:
        units = _units(items)
        if shuffle_questions:
            rng.shuffle(units)
        out_items: list[dict[str, object]] = []
        for item in (i for unit in units for i in unit):
            number += 1
            order: list[int] | None = None
            if item.type in CHOICE_TYPES and item.choices:
                order = (
                    permute_choices(item.choices, rng)
                    if shuffle_choices
                    else list(range(len(item.choices)))
                )
            out_items.append(
                {
                    "item_id": str(item.item_id),
                    "question_id": str(item.question_id),
                    "number": number,
                    "points": item.points,
                    "choice_order": order,
                }
            )
        out_sections.append({"section_id": str(section_id), "items": out_items})
    return {"sections": out_sections}


def version_label(language: str, index: int) -> str:
    return display_label(language, index)


@dataclass(frozen=True)
class KeyQuestion:
    type: str
    correct_flags: Sequence[bool | None]
    answer_text: str | None


def answer_key_entry(
    layout_item: dict[str, object], question: KeyQuestion, language: str
) -> tuple[dict[str, object], str | None]:
    """Answer-key row for one layout item, plus a warning when an MCQ has no known answer."""
    order = layout_item["choice_order"]
    correct: list[str] | None = None
    warning: str | None = None
    if question.type in CHOICE_TYPES:
        assert isinstance(order, list)  # noqa: S101 -- layouts of MCQs always carry an order
        labels = [
            display_label(language, position)
            for position, source in enumerate(order)
            if question.correct_flags[source] is True
        ]
        if labels:
            correct = labels
        else:
            warning = f"question {layout_item['question_id']} has no known correct choice"
    entry: dict[str, object] = {
        "number": layout_item["number"],
        "question_id": layout_item["question_id"],
        "type": question.type,
        "correct": correct,
        "answer_text": question.answer_text,
        "points": layout_item["points"],
    }
    return entry, warning
