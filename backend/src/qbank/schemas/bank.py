from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qbank.models import Language
from qbank.schemas.common import Output


class ValidationIssueOut(Output):
    code: str
    severity: str
    message: str
    details: dict[str, object]
    resolved_at: datetime | None
    resolved_by: UUID | None


class QuestionOut(Output):
    subject_id: UUID
    source_id: UUID
    stimulus_id: UUID | None
    stimulus_position: int | None
    position: int
    number_label: str
    type: str
    stem: str
    choices: list[dict[str, object]]
    answer: str | None
    language: Language
    regions: list[dict[str, object]]
    status: str
    confidence: float
    duplicate_of_id: UUID | None
    difficulty: int | None
    difficulty_reason: str | None
    tags: list[str]
    issues: list[ValidationIssueOut]


class StimulusOut(Output):
    source_id: UUID
    kind: str
    content: str
    regions: list[dict[str, object]]
    status: str


class IssuesCount(BaseModel):
    error: int = 0
    warning: int = 0


class BankQuestionOut(BaseModel):
    id: UUID
    subject_id: UUID
    number_label: str
    type: str
    stem_preview: str
    choices_count: int
    difficulty: int | None
    tags: list[str]
    status: str
    chapter_id: UUID | None
    chapter_title: str | None
    lesson_id: UUID | None
    lesson_title: str | None
    source_id: UUID | None
    source_title: str | None
    source_page: int | None
    stimulus_id: UUID | None
    has_figure: bool
    issues_count: IssuesCount


class ChapterFacet(BaseModel):
    id: UUID
    title: str
    count: int


class LessonFacet(BaseModel):
    id: UUID
    chapter_id: UUID
    title: str
    count: int


class SourceFacet(BaseModel):
    id: UUID
    title: str
    count: int


class TagCount(BaseModel):
    tag: str
    count: int


class BankFacets(BaseModel):
    total: int
    chapters: list[ChapterFacet]
    lessons: list[LessonFacet]
    types: dict[str, int]
    difficulties: dict[int, int]
    statuses: dict[str, int]
    sources: list[SourceFacet]
    tags: list[TagCount]


class BankSearchOut(BaseModel):
    items: list[BankQuestionOut]
    next_cursor: str | None
    total: int
    match_mode: Literal["fts", "fuzzy"]
    facets: BankFacets | None = None


class BankStatsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
    by_difficulty: dict[int, int]
    approved_by_chapter: list[ChapterFacet]
    approved_by_lesson: list[LessonFacet]


class QuestionsMove(BaseModel):
    ids: list[UUID] = Field(min_length=1)
    lesson_id: UUID


class QuestionsMoveOut(BaseModel):
    moved: int
