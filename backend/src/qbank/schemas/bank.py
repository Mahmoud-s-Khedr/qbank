from datetime import datetime
from uuid import UUID

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
