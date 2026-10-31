"""Validated vision output and conversion to the persisted region convention."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Box = tuple[int, int, int, int]
Confidence = Annotated[float, Field(ge=0, le=1)]


def to_region_box(box: Box) -> list[float]:
    """Convert Gemini's y/x coordinates to normalized, ordered x/y coordinates."""
    ymin, xmin, ymax, xmax = (max(0, min(1000, value)) for value in box)
    x0, x1 = sorted((xmin, xmax))
    y0, y1 = sorted((ymin, ymax))
    return [x0 / 1000, y0 / 1000, x1 / 1000, y1 / 1000]


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Heading(ExtractionModel):
    level: Literal["book", "unit", "chapter", "lesson", "exam", "section"]
    text: str
    box_2d: Box


class Stimulus(ExtractionModel):
    ref: str
    kind: Literal["passage", "poem", "figure", "table", "case"]
    intro: str | None
    content: str
    box_2d: Box
    continues_from_previous: bool
    continues_on_next: bool


class Choice(ExtractionModel):
    label: str
    content: str


class Answer(ExtractionModel):
    labels: list[str]
    text: str | None


class Figure(ExtractionModel):
    box_2d: Box
    kind: Literal["diagram", "chart", "table", "photo"]


class Question(ExtractionModel):
    number_label: str
    type: Literal[
        "mcq_single",
        "mcq_multi",
        "true_false",
        "fill_blank",
        "short_answer",
        "essay",
        "matching",
        "ordering",
    ]
    stem: str
    choices: list[Choice]
    answer: Answer | None
    stimulus_ref: str | None
    figures: list[Figure]
    box_2d: Box
    continues_from_previous: bool
    continues_on_next: bool
    confidence: Confidence


class AnswerKeyEntry(ExtractionModel):
    section: str | None
    number_label: str
    labels: list[str]
    text: str | None


class PageExtraction(ExtractionModel):
    page_kind: Literal[
        "cover",
        "blank",
        "toc",
        "section_divider",
        "questions",
        "answer_key",
        "answer_sheet",
        "other",
    ]
    headings: list[Heading]
    stimuli: list[Stimulus]
    questions: list[Question]
    answer_key_entries: list[AnswerKeyEntry]
    page_confidence: Confidence
    notes: str
