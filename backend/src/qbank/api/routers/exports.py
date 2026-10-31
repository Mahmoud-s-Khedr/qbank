from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError

from qbank.api.deps import DB, Admin, Current
from qbank.models import Asset
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
from qbank.services.errors import Invalid
from qbank.services.exports import DOCX_TYPE
from qbank.services.unit_of_work import save
from qbank.storage import get_store

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
    responses={
        200: {
            "content": {"application/pdf": {}, DOCX_TYPE: {}},
            "description": "The exported PDF or DOCX file",
        }
    },
)
def download_export(id: UUID, db: DB, user: Current) -> StreamingResponse:
    chunks, disposition, size, media_type = service.download(db, user, id)
    headers = {"Content-Disposition": disposition}
    if size is not None:
        headers["Content-Length"] = str(size)
    return StreamingResponse(chunks, media_type=media_type, headers=headers)


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


@router.post("/exam-templates/{id}/logo", response_model=TemplateOut)
async def upload_logo(id: UUID, file: UploadFile, db: DB, user: Admin) -> TemplateOut:
    template = templates.template_for(db, user.org_id, id)
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024 or file.content_type not in {
        "image/png",
        "image/jpeg",
        "image/webp",
    }:
        raise Invalid("invalid_logo")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise Invalid("invalid_logo")
            image.thumbnail((600, image.height))
            image.load()
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            width, height = image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise Invalid("invalid_logo") from None
    asset_id = uuid4()
    key = f"orgs/{user.org_id}/logos/{asset_id}.png"
    get_store().put_bytes(key, output.getvalue(), "image/png")
    asset = Asset(
        id=asset_id,
        org_id=user.org_id,
        kind="logo",
        image_key=key,
        region=[],
        width=width,
        height=height,
        pipeline_generated=False,
    )
    db.add(asset)
    db.flush()
    template.logo_asset_id = asset_id
    save(db)
    return TemplateOut.model_validate(template, from_attributes=True)
