from uuid import UUID

from pydantic import BaseModel

from qbank.models import PageKind, PageStatus, SourceStatus
from qbank.schemas.common import Output


class SourceOut(Output):
    subject_id: UUID
    title: str
    grade: str | None
    page_count: int | None
    status: SourceStatus
    stage: str | None
    error: str | None
    cost_usd: float


class SourceDetail(SourceOut):
    page_counts: dict[str, int]


class UploadResult(BaseModel):
    source: SourceOut
    job_id: UUID


class PageOut(Output):
    page_number: int
    status: PageStatus
    page_kind: PageKind | None
    error: str | None
    width_px: int | None
    height_px: int | None
    dpi: int | None


class JobOut(Output):
    kind: str
    status: str
    progress: dict[str, object]
    error: str | None
    ref_id: UUID
