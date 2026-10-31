from typing import BinaryIO, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qbank.api.pagination import paginate
from qbank.config import get_settings
from qbank.db import new_uuid
from qbank.models import Job, Source, SourcePage, SourceStatus, Subject
from qbank.pipeline import orchestrator
from qbank.schemas.sources import SourceDetail, SourceOut
from qbank.services.errors import Conflict, DomainError, Invalid
from qbank.services.scoping import get
from qbank.services.unit_of_work import found, save
from qbank.storage import get_store, keys


class TooLargeError(DomainError):
    status = 413
    code = "file_too_large"


def source(db: Session, org_id: UUID, source_id: UUID) -> Source:
    return found(db.scalar(select(Source).where(Source.id == source_id, Source.org_id == org_id)))


def upload(  # noqa: PLR0913, PLR0917 -- upload fields are independent inputs.
    db: Session, org_id: UUID, subject_id: UUID, title: str, grade: str | None, fileobj: BinaryIO
) -> tuple[Source, UUID]:
    found(get(db, Subject, org_id, subject_id))
    if fileobj.read(5) != b"%PDF-":
        raise Invalid("invalid_pdf")
    fileobj.seek(0, 2)
    if fileobj.tell() > get_settings().max_upload_mb * 1024 * 1024:
        raise TooLargeError()
    fileobj.seek(0)
    sid = new_uuid()
    key = keys.original(org_id, sid)
    get_store().put(key, fileobj, "application/pdf")
    item = Source(
        id=sid,
        org_id=org_id,
        subject_id=subject_id,
        title=title,
        grade=grade,
        file_key=key,
        status=SourceStatus.rendering,
        stage=orchestrator.STAGES[0].name,
    )
    job = Job(org_id=org_id, kind="ingest", status="running", ref_id=sid)
    try:
        db.add(item)
        db.flush()
        db.add(job)
        save(db)
    except Exception:
        db.rollback()
        get_store().delete(key)
        raise
    orchestrator.STAGES[0].start(str(sid))
    return item, job.id


def listing(  # noqa: PLR0913, PLR0917 -- pagination and filters are independent.
    db: Session,
    org_id: UUID,
    subject_id: UUID | None,
    status: SourceStatus | None,
    cursor: str | None,
    limit: int,
) -> dict[str, object]:
    stmt = select(Source).where(Source.org_id == org_id)
    if subject_id:
        stmt = stmt.where(Source.subject_id == subject_id)
    if status:
        stmt = stmt.where(Source.status == status)
    try:
        items, next_cursor = paginate(db, stmt, Source, cursor, limit)
    except ValueError:
        raise Invalid("invalid_cursor") from None
    return {"items": items, "next_cursor": next_cursor}


def counts(db: Session, source_id: UUID) -> dict[str, int]:
    rows = db.execute(
        select(SourcePage.status, func.count())
        .where(SourcePage.source_id == source_id)
        .group_by(SourcePage.status)
    )
    return {status.value: count for status, count in rows}


def detail(db: Session, org_id: UUID, source_id: UUID) -> SourceDetail:
    item = source(db, org_id, source_id)
    return SourceDetail(
        **SourceOut.model_validate(item).model_dump(), page_counts=counts(db, source_id)
    )


def delete(db: Session, org_id: UUID, source_id: UUID) -> None:
    item = source(db, org_id, source_id)
    get_store().delete_prefix(keys.prefix(org_id, source_id))
    db.delete(item)
    save(db)


def pages(db: Session, org_id: UUID, source_id: UUID) -> list[SourcePage]:
    source(db, org_id, source_id)
    return list(
        db.scalars(
            select(SourcePage)
            .where(SourcePage.source_id == source_id)
            .order_by(SourcePage.page_number)
        )
    )


def page(db: Session, org_id: UUID, source_id: UUID, number: int) -> SourcePage:
    source(db, org_id, source_id)
    return found(
        db.scalar(
            select(SourcePage).where(
                SourcePage.source_id == source_id, SourcePage.page_number == number
            )
        )
    )


def job(db: Session, org_id: UUID, job_id: UUID) -> Job:
    item = found(db.scalar(select(Job).where(Job.id == job_id, Job.org_id == org_id)))
    item.progress = cast(dict[str, object], counts(db, item.ref_id))
    return item


def resume(db: Session, org_id: UUID, source_id: UUID) -> Source:
    item = found(
        db.scalar(
            select(Source).where(Source.id == source_id, Source.org_id == org_id).with_for_update()
        )
    )
    if item.status != SourceStatus.paused:
        raise Conflict("source_not_paused")
    stage = next((stage for stage in orchestrator.STAGES if stage.name == item.stage), None)
    if stage is None:
        raise Conflict("invalid_stage")
    item.status = stage.status
    item.error = None
    job = db.scalar(select(Job).where(Job.ref_id == source_id, Job.kind == "ingest"))
    if job:
        job.status = "running"
        job.error = None
    save(db)
    stage.start(str(source_id))
    return item
