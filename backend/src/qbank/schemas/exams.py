from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qbank.schemas.common import Output


class ExamHeader(BaseModel):
    school_name: str = ""
    exam_title: str = ""
    subject_label: str = ""
    grade: str = ""
    date: str = ""
    duration_minutes: int | None = Field(default=None, ge=1, le=1000)
    instructions: str = ""


class ExamLayout(BaseModel):
    columns: Literal[1, 2] = 1
    font_size_pt: int = Field(default=12, ge=10, le=16)
    digits: Literal["arabic", "western"] = "arabic"
    answer_space_lines: int = Field(default=4, ge=0, le=20)
    choices_per_row: Literal["auto", 1, 2, 4] = "auto"


class ExamSettings(BaseModel):
    header: ExamHeader = Field(default_factory=ExamHeader)
    layout: ExamLayout = Field(default_factory=ExamLayout)
    language: Literal["ar", "en"] = "ar"


class ExamIn(BaseModel):
    title: str = Field(min_length=1)
    subject_id: UUID
    settings: ExamSettings | None = None


class ExamUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    settings: ExamSettings | None = None
    status: Literal["draft", "final"] | None = None


class SectionIn(BaseModel):
    title: str = Field(min_length=1)
    instructions: str | None = None


class SectionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    instructions: str | None = None


class ItemsIn(BaseModel):
    question_ids: list[UUID] = Field(min_length=1)
    section_id: UUID | None = None
    points: float = Field(default=1, ge=0)


class ItemUpdate(BaseModel):
    points: float | None = Field(default=None, ge=0)
    section_id: UUID | None = None
    position: int | None = Field(default=None, ge=0)


class ReorderSections(BaseModel):
    ids: list[UUID]


class ReorderItems(BaseModel):
    section_id: UUID
    ids: list[UUID]


class StimulusContent(BaseModel):
    id: UUID
    kind: str
    content: str


class QuestionContent(BaseModel):
    id: UUID
    number_label: str
    type: str
    stem: str
    choices: list[dict[str, object]]
    answer: str | None
    difficulty: int | None
    tags: list[str]
    stimulus_id: UUID | None
    stimulus_position: int | None


class ItemOut(BaseModel):
    id: UUID
    section_id: UUID
    question_id: UUID
    position: int
    points: float
    origin: str
    question: QuestionContent
    stimulus: StimulusContent | None = None  # only on the first item of a stimulus group


class SectionOut(BaseModel):
    id: UUID
    title: str
    position: int
    instructions: str | None
    items: list[ItemOut]


class VersionOut(BaseModel):
    id: UUID
    label: str
    seed: int
    exam_revision: int
    stale: bool
    created_at: datetime


class ExamSummary(Output):
    title: str
    subject_id: UUID
    owner_id: UUID
    status: str
    revision: int
    question_count: int
    total_points: float


class ExamDetail(ExamSummary):
    settings: ExamSettings
    blueprint: dict[str, object] | None
    sections: list[SectionOut]
    versions: list[VersionOut]


class BlueprintRow(BaseModel):
    chapter_ids: list[UUID] = Field(default_factory=list)
    lesson_ids: list[UUID] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    difficulty_min: int | None = None
    difficulty_max: int | None = None
    tags_any: list[str] = Field(default_factory=list)
    count: int = Field(ge=1, le=500)
    points: float = Field(default=1, ge=0)
    section_id: UUID | None = None


class Blueprint(BaseModel):
    rows: list[BlueprintRow] = Field(min_length=1)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    exclude_question_ids: list[UUID] = Field(default_factory=list)
    exclude_used_in_my_exams: bool = False


class BlueprintRowResult(BaseModel):
    requested: int
    selected: list[UUID]
    shortfall: int
    available: int


class BlueprintResult(BaseModel):
    rows: list[BlueprintRowResult]
    seed: int


class VersionsIn(BaseModel):
    count: int = Field(ge=1, le=10)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1000)
    shuffle_questions: bool = True
    shuffle_choices: bool = True
    keep_first_as_original: bool = False


class AnswerKeyEntry(BaseModel):
    number: int
    question_id: UUID
    type: str
    correct: list[str] | None
    answer_text: str | None
    points: float


class AnswerKey(BaseModel):
    label: str
    items: list[AnswerKeyEntry]
    warnings: list[str]
