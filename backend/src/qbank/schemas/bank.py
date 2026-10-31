from uuid import UUID

from qbank.models import Language
from qbank.schemas.common import Output


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


class StimulusOut(Output):
    source_id: UUID
    kind: str
    content: str
    regions: list[dict[str, object]]
    status: str
