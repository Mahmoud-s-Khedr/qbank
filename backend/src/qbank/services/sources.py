import tempfile
from shutil import copyfileobj
from typing import BinaryIO, cast
from uuid import UUID

import pymupdf
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from qbank.api.pagination import paginate
from qbank.config import get_settings
from qbank.db import new_uuid
from qbank.models import (
    Job,
    LLMCall,
    Question,
    Source,
    SourcePage,
    SourceStatus,
    Subject,
    ValidationIssue,
)
from qbank.pipeline import orchestrator
from qbank.schemas.sources import IssueSummary, SourceDetail, SourceOut, SourceSummary
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
    try:
        # Keep large uploads on disk rather than making an unbounded in-memory copy.
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary:
            copyfileobj(fileobj, temporary)
            temporary.flush()
            # PyMuPDF does not type its document constructor.
            with pymupdf.open(temporary.name) as document:  # type: ignore[no-untyped-call]
                if document.is_encrypted or document.metadata.get("encryption"):
                    raise Invalid("encrypted_pdf")
    except pymupdf.FileDataError:
        # Rendering performs the remaining PDF validation asynchronously.
        pass
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


def summary(db: Session, org_id: UUID, source_id: UUID) -> SourceSummary:
    source(db, org_id, source_id)
    q_rows = db.execute(
        select(Question.status, func.count())
        .where(Question.source_id == source_id, Question.org_id == org_id)
        .group_by(Question.status)
    )
    question_counts = {str(status): int(count) for status, count in q_rows}

    issue_rows = db.execute(
        select(ValidationIssue.code, ValidationIssue.severity, func.count())
        .join(Question, ValidationIssue.question_id == Question.id)
        .where(Question.source_id == source_id, Question.org_id == org_id)
        .group_by(ValidationIssue.code, ValidationIssue.severity)
        .order_by(ValidationIssue.code.asc(), ValidationIssue.severity.asc())
    )
    issues: list[IssueSummary] = []
    issues_by_code: dict[str, int] = {}
    issues_by_severity: dict[str, int] = {}
    for code, severity, count in issue_rows:
        cnt = int(count)
        issues.append(IssueSummary(code=str(code), severity=str(severity), count=cnt))
        issues_by_code[str(code)] = issues_by_code.get(str(code), 0) + cnt
        issues_by_severity[str(severity)] = issues_by_severity.get(str(severity), 0) + cnt

    spend_rows = db.execute(
        select(LLMCall.stage, func.coalesce(func.sum(LLMCall.cost_usd), 0))
        .where(LLMCall.source_id == source_id)
        .group_by(LLMCall.stage)
    )
    spend_by_stage = {str(stage): float(cost) for stage, cost in spend_rows}

    return SourceSummary(
        question_counts=question_counts,
        issues_by_code=issues_by_code,
        issues_by_severity=issues_by_severity,
        issues=issues,
        spend_by_stage=spend_by_stage,
    )


def delete(db: Session, org_id: UUID, source_id: UUID) -> None:
    item = source(db, org_id, source_id)
    get_store().delete_prefix(keys.prefix(org_id, source_id))
    db.execute(update(LLMCall).where(LLMCall.source_id == source_id).values(source_id=None))
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
    if item.kind == "ingest":
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
