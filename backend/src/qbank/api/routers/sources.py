import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Header, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from qbank.api.deps import DB, Current, Writer
from qbank.config import get_settings
from qbank.db import get_engine
from qbank.models import Asset, Job, Question, Source, SourcePage, SourceStatus, Stimulus
from qbank.schemas.bank import QuestionOut, StimulusOut
from qbank.schemas.common import Page
from qbank.schemas.sources import (
    JobOut,
    PageDetail,
    PageOut,
    SourceDetail,
    SourceOut,
    SourceSummary,
    UploadResult,
)
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


@router.get("/sources/{id}/summary", response_model=SourceSummary)
def summary(id: UUID, db: DB, user: Current) -> SourceSummary:
    return service.summary(db, user.org_id, id)


@router.post("/sources/{id}/resume", response_model=SourceOut)
def resume(id: UUID, db: DB, user: Writer) -> Source:
    return service.resume(db, user.org_id, id)


@router.get("/sources/{id}/pages/{number}", response_model=PageDetail)
def page_detail(id: UUID, number: int, db: DB, user: Current) -> SourcePage:
    return service.page(db, user.org_id, id, number)


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


@router.get("/sources/{id}/questions", response_model=list[QuestionOut])
def questions(id: UUID, db: DB, user: Current) -> list[Question]:
    service.source(db, user.org_id, id)
    return list(
        db.scalars(
            select(Question)
            .where(Question.source_id == id, Question.org_id == user.org_id)
            .order_by(Question.position)
        )
    )


@router.get("/questions/{id}", response_model=QuestionOut)
def question(id: UUID, db: DB, user: Current) -> Question:
    return found(
        db.scalar(select(Question).where(Question.id == id, Question.org_id == user.org_id))
    )


@router.get("/sources/{id}/stimuli", response_model=list[StimulusOut])
def stimuli(id: UUID, db: DB, user: Current) -> list[Stimulus]:
    service.source(db, user.org_id, id)
    return list(
        db.scalars(
            select(Stimulus)
            .where(Stimulus.source_id == id, Stimulus.org_id == user.org_id)
            .order_by(Stimulus.created_at, Stimulus.id)
        )
    )


@router.get("/assets/{id}/image")
def asset_image(
    id: UUID, db: DB, user: Current, if_none_match: Annotated[str | None, Header()] = None
) -> Response:
    asset = found(db.scalar(select(Asset).where(Asset.id == id, Asset.org_id == user.org_id)))
    tag = f'"{asset.id}-{asset.updated_at.timestamp()}"'
    headers = {"ETag": tag, "Cache-Control": "private, max-age=86400"}
    if if_none_match == tag:
        return Response(status_code=304, headers=headers)
    stream = get_store().open(asset.image_key)

    def chunks() -> Iterator[bytes]:
        with stream:
            while chunk := stream.read(65536):
                yield chunk

    return StreamingResponse(chunks(), media_type="image/webp", headers=headers)


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
