from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qbank.schemas.common import Output
from qbank.schemas.exams import ExamHeader

ExportKind = Literal["pdf", "answer_key_pdf", "bubble_sheet_pdf"]
ExportStatus = Literal["pending", "ready", "failed"]


def _default_kinds() -> list[ExportKind]:
    return ["pdf"]


class ExportsIn(BaseModel):
    versions: list[str] | Literal["all"] = "all"
    kinds: list[ExportKind] = Field(default_factory=_default_kinds, min_length=1)


class ExportOut(Output):
    exam_id: UUID
    exam_version_id: UUID
    version_label: str
    kind: ExportKind
    status: ExportStatus
    error: str | None
    exam_revision: int
    size_bytes: int | None
    stale: bool


class ExportBatch(BaseModel):
    """Accepted export requests; poll ``GET /exams/{id}/exports`` until each is ready or failed."""

    exports: list[ExportOut]


class TemplateIn(BaseModel):
    name: str = Field(min_length=1)
    header: ExamHeader = Field(default_factory=ExamHeader)
    logo_asset_id: UUID | None = None


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    header: ExamHeader | None = None
    logo_asset_id: UUID | None = None


class TemplateOut(Output):
    name: str
    header: ExamHeader
    logo_asset_id: UUID | None
