import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from qbank.api.deps import DB, Current, Writer
from qbank.config import get_settings
from qbank.db import get_engine
from qbank.models import Job, SourcePage, SourceStatus
from qbank.schemas.common import Page
from qbank.schemas.sources import JobOut, PageOut, SourceDetail, SourceOut, UploadResult
from qbank.services import sources as service
from qbank.services.unit_of_work import found
from qbank.storage import get_store, keys

router = APIRouter(prefix="/api/v1")
KEEPALIVE_SECONDS = 15


@router.post("/sources", response_model=UploadResult, status_code=202)
def upload(  # noqa: PLR0913, PLR0917 -- multipart fields are separate API inputs.
    db: DB,
    user: Writer,
    file: Annotated[UploadFile, File()],
    subject_id: Annotated[UUID, Form()],
    title: Annotated[str, Form()],
    grade: Annotated[str | None, Form()] = None,
) -> UploadResult:
    item, job_id = service.upload(db, user.org_id, subject_id, title, grade, file.file)
    return UploadResult(source=SourceOut.model_validate(item), job_id=job_id)


@router.get("/sources", response_model=Page[SourceOut])
def listing(  # noqa: PLR0913, PLR0917 -- independent query parameters.
    db: DB,
    user: Current,
    subject_id: UUID | None = None,
    status: SourceStatus | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, object]:
    return service.listing(db, user.org_id, subject_id, status, cursor, limit)


@router.get("/sources/{id}", response_model=SourceDetail)
def detail(id: UUID, db: DB, user: Current) -> SourceDetail:
    return service.detail(db, user.org_id, id)


@router.delete("/sources/{id}", status_code=204)
def delete(id: UUID, db: DB, user: Writer) -> None:
    service.delete(db, user.org_id, id)


@router.get("/sources/{id}/pages", response_model=list[PageOut])
def pages(id: UUID, db: DB, user: Current) -> list[SourcePage]:
    return service.pages(db, user.org_id, id)


@router.get("/sources/{id}/pages/{number}/image")
def image(  # noqa: PLR0913, PLR0917 -- path, variant and conditional request inputs.
    id: UUID,
    number: int,
    db: DB,
    user: Current,
    variant: Literal["display", "hires"] = "display",
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    page = service.page(db, user.org_id, id, number)
    found(page.image_key)
    tag = f'"{page.id}-{page.updated_at.timestamp()}-{variant}"'
    headers = {"ETag": tag, "Cache-Control": "private, max-age=86400"}
    if if_none_match == tag:
        return Response(status_code=304, headers=headers)
    key = keys.page(user.org_id, id, number, hires=variant == "hires")
    stream = get_store().open(key)

    def chunks() -> Iterator[bytes]:
        with stream:
            while chunk := stream.read(65536):
                yield chunk

    return StreamingResponse(
        chunks(), media_type="image/png" if variant == "hires" else "image/webp", headers=headers
    )


@router.get("/jobs/{id}", response_model=JobOut)
def job(id: UUID, db: DB, user: Current) -> Job:
    return service.job(db, user.org_id, id)


def snapshot(org_id: UUID, source_id: UUID) -> dict[str, object]:
    with Session(get_engine()) as db:
        item = service.detail(db, org_id, source_id)
        return {"status": item.status.value, "stage": item.stage, "page_counts": item.page_counts}


@router.get("/sources/{id}/events")
async def events(id: UUID, db: DB, user: Current) -> StreamingResponse:
    service.source(db, user.org_id, id)
    org_id = user.org_id

    async def generate() -> AsyncIterator[str]:
        previous = ""
        keepalive = time.monotonic()
        while True:
            state = await run_in_threadpool(snapshot, org_id, id)
            data = json.dumps(state, sort_keys=True)
            if data != previous:
                yield f"event: progress\ndata: {data}\n\n"
                previous = data
            if state["status"] in ("ready", "failed", "paused"):
                break
            if time.monotonic() - keepalive >= KEEPALIVE_SECONDS:
                yield ": keep-alive\n\n"
                keepalive = time.monotonic()
            await asyncio.sleep(get_settings().sse_interval)

    return StreamingResponse(generate(), media_type="text/event-stream")
