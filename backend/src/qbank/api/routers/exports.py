from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from qbank.api.deps import DB, Admin, Current
from qbank.schemas.common import Page
from qbank.schemas.exports import (
    ExportBatch,
    ExportOut,
    ExportsIn,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
)
from qbank.services import exam_templates as templates
from qbank.services import exports as service

router = APIRouter(prefix="/api/v1", tags=["exports"])


@router.post("/exams/{id}/exports", response_model=ExportBatch, status_code=202)
def request_exports(id: UUID, data: ExportsIn, db: DB, user: Current) -> ExportBatch:
    return service.request(db, user, id, data)


@router.get("/exams/{id}/exports", response_model=list[ExportOut])
def list_exports(id: UUID, db: DB, user: Current) -> list[ExportOut]:
    return service.listing(db, user, id)


@router.get(
    "/exports/{id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/pdf": {}}, "description": "The PDF file"}},
)
def download_export(id: UUID, db: DB, user: Current) -> StreamingResponse:
    chunks, disposition, size = service.download(db, user, id)
    headers = {"Content-Disposition": disposition}
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(chunks, media_type="application/pdf", headers=headers)


@router.delete("/exports/{id}", status_code=204)
def delete_export(id: UUID, db: DB, user: Current) -> None:
    service.delete(db, user, id)


@router.get("/exam-templates", response_model=Page[TemplateOut])
def list_templates(
    db: DB, user: Current, cursor: str | None = None, limit: int = Query(50, ge=1, le=100)
) -> dict[str, object]:
    return templates.listing(db, user, cursor, limit)


@router.post("/exam-templates", response_model=TemplateOut, status_code=201)
def create_template(data: TemplateIn, db: DB, user: Admin) -> TemplateOut:
    return templates.create(db, user, data)


@router.get("/exam-templates/{id}", response_model=TemplateOut)
def get_template(id: UUID, db: DB, user: Current) -> TemplateOut:
    return templates.get(db, user, id)


@router.patch("/exam-templates/{id}", response_model=TemplateOut)
def edit_template(id: UUID, data: TemplateUpdate, db: DB, user: Admin) -> TemplateOut:
    return templates.edit(db, user, id, data)


@router.delete("/exam-templates/{id}", status_code=204)
def delete_template(id: UUID, db: DB, user: Admin) -> None:
    templates.delete(db, user, id)
