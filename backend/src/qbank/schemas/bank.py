from datetime import datetime
from uuid import UUID

from pydantic import Field

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
    source_id: UUID | None
    chapter_id: UUID | None
    lesson_id: UUID | None
    explanation: str | None
    difficulty_source: str | None
    version: int
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
    metadata: dict[str, object] = Field(validation_alias="metadata_json")
