"""Request and response shapes for the review APIs (T12)."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qbank.pipeline.schema import Question as ExtractedQuestion
from qbank.schemas.bank import QuestionOut, ValidationIssueOut
from qbank.schemas.common import Output

QuestionType = Literal[
    "mcq_single",
    "mcq_multi",
    "true_false",
    "fill_blank",
    "short_answer",
    "essay",
    "matching",
    "ordering",
]
MAX_BULK = 500


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Region(Strict):
    """A normalized x0,y0,x1,y1 box (fractions of the page)."""

    box: list[float] = Field(min_length=4, max_length=4)

    @field_validator("box")
    @classmethod
    def _ordered(cls, box: list[float]) -> list[float]:
        x0, y0, x1, y1 = box
        if not all(0 <= value <= 1 for value in box) or x1 <= x0 or y1 <= y0:
            raise ValueError("box must be ordered x0,y0,x1,y1 within 0..1")
        return box


class FigureIn(Region):
    page_id: UUID


class ChoiceIn(Strict):
    label: str
    content: str
    is_correct: bool | None = None
    pinned: bool | None = None


class QuestionPatch(Strict):
    """Partial update; only the fields present in the body change."""

    version: int
    stem: str | None = None
    choices: list[ChoiceIn] | None = None
    answer: str | None = None
    explanation: str | None = None
    type: QuestionType | None = None
    number_label: str | None = None
    chapter_id: UUID | None = None
    lesson_id: UUID | None = None
    difficulty: Annotated[int, Field(ge=1, le=5)] | None = None
    tags: list[str] | None = None
    stimulus_id: UUID | None = None
    stimulus_position: int | None = None
    regions: list[dict[str, object]] | None = None

    @model_validator(mode="after")
    def _required_not_null(self) -> "QuestionPatch":
        for name in ("stem", "choices", "type", "number_label", "tags", "regions"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class QuestionCreate(Strict):
    subject_id: UUID
    type: QuestionType
    stem: str
    choices: list[ChoiceIn] = Field(default_factory=list)
    answer: str | None = None
    explanation: str | None = None
    number_label: str = ""
    chapter_id: UUID | None = None
    lesson_id: UUID | None = None
    difficulty: Annotated[int, Field(ge=1, le=5)] | None = None
    tags: list[str] = Field(default_factory=list)


class ApproveIn(Strict):
    force: bool = False
    version: int | None = None


class RejectIn(Strict):
    reason: str | None = None
    version: int | None = None


class ReopenIn(Strict):
    version: int | None = None


class BulkMetadata(Strict):
    chapter_id: UUID | None = None
    lesson_id: UUID | None = None
    difficulty: Annotated[int, Field(ge=1, le=5)] | None = None
    tags_add: list[str] = Field(default_factory=list)
    tags_remove: list[str] = Field(default_factory=list)


class BulkIn(Strict):
    ids: list[UUID] = Field(min_length=1, max_length=MAX_BULK)
    action: Literal["approve", "reject", "set_metadata"]
    metadata: BulkMetadata | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _metadata_required(self) -> "BulkIn":
        if self.action == "set_metadata" and self.metadata is None:
            raise ValueError("metadata is required for set_metadata")
        return self


class BulkResult(BaseModel):
    id: UUID
    ok: bool
    code: str | None = None
    status: str | None = None
    version: int | None = None


class BulkOut(BaseModel):
    results: list[BulkResult]
    succeeded: int
    failed: int


class StemSplit(Strict):
    field: Literal["stem"]
    offset: int = Field(ge=0)


class ChoiceSplit(Strict):
    choice_index: int = Field(ge=0)


class SplitIn(Strict):
    at: StemSplit | ChoiceSplit
    number_label: str | None = None


class SplitOut(BaseModel):
    first: QuestionOut
    second: QuestionOut


class MergeIn(Strict):
    ids: list[UUID] = Field(min_length=2, max_length=2)


class QuestionEventOut(Output):
    question_id: UUID
    user_id: UUID | None
    action: str
    diff: dict[str, object]


class AssetOut(Output):
    source_page_id: UUID | None
    kind: str
    region: list[float]
    width: int
    height: int
    pipeline_generated: bool


class StimulusPatch(Strict):
    content: str | None = None
    kind: str | None = None
    intro: str | None = None

    @model_validator(mode="after")
    def _required_not_null(self) -> "StimulusPatch":
        for name in ("content", "kind"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class StimulusCreate(Region):
    source_id: UUID
    page_id: UUID
    kind: Literal["passage", "poem", "figure", "table", "case"]
    content: str = ""
    intro: str | None = None


class ReextractIn(Strict):
    model: str | None = None


class ReextractOut(BaseModel):
    job_id: UUID


class ExtractRegionIn(Region):
    model: str | None = None


class DraftQuestion(ExtractedQuestion):
    """An extracted question, not yet persisted; confirm it with POST /questions."""


class ProposalOut(Output):
    page_id: UUID
    source_id: UUID
    page_number: int
    model: str
    cost_usd: float
    created_by: UUID | None
    status: str
    extraction: dict[str, object]


class FieldChange(BaseModel):
    before: object
    after: object


class ChangedItem(BaseModel):
    number_label: str
    question_id: UUID
    status: str
    fields: dict[str, FieldChange]


class AddedItem(BaseModel):
    number_label: str
    question: dict[str, object]


class RemovedItem(BaseModel):
    number_label: str
    question_id: UUID
    status: str


class ProposalDiff(BaseModel):
    changed: list[ChangedItem]
    added: list[AddedItem]
    removed: list[RemovedItem]
    unchanged: list[str]


class ProposalDetail(BaseModel):
    proposal: ProposalOut
    diff: ProposalDiff


class AcceptIn(Strict):
    number_labels: list[str] | None = None


class SkippedItem(BaseModel):
    number_label: str
    reason: str


class AcceptOut(BaseModel):
    proposal: ProposalOut
    applied: list[str]
    skipped: list[SkippedItem]


class QueueItem(BaseModel):
    id: UUID
    number_label: str
    position: int
    page: int | None
    status: str
    confidence: float
    issues: dict[str, int]


class QueueTotals(BaseModel):
    count: int
    by_status: dict[str, int]
    by_severity: dict[str, int]


class ReviewQueue(BaseModel):
    items: list[QueueItem]
    totals: QueueTotals


class IssueOut(ValidationIssueOut):
    question_id: UUID


class ErrorConflict(BaseModel):
    """Documented 409 body for version conflicts."""

    code: str
    current: QuestionOut
