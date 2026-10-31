"""Export requests, listing, download and deletion. Rendering itself runs in the worker."""

import re
from collections.abc import Iterator
from typing import BinaryIO
from urllib.parse import quote
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.exams.versions import CHOICE_TYPES
from qbank.export.builder import render_export
from qbank.models import Exam, ExamItem, ExamVersion, Export, Question, User
from qbank.schemas.exports import ExportBatch, ExportOut, ExportsIn
from qbank.services import exams as exams_service
from qbank.services.errors import Conflict, Invalid, NotFound
from qbank.services.unit_of_work import found, save
from qbank.storage import ObjectStore, get_store, keys

logger = structlog.get_logger()
CHUNK = 64 * 1024
MAX_ERROR = 500
UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]+')
PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_KINDS = frozenset({"docx", "answer_key_docx"})


def media_type(kind: str) -> str:
    return DOCX_TYPE if kind in DOCX_KINDS else PDF_TYPE


def extension(kind: str) -> str:
    return "docx" if kind in DOCX_KINDS else "pdf"


def enqueue(export_ids: list[UUID]) -> None:
    from qbank.worker import render_exports  # noqa: PLC0415 -- avoids a worker import cycle.

    render_exports.send([str(i) for i in export_ids])


def _out(export: Export, version: ExamVersion, exam: Exam) -> ExportOut:
    return ExportOut(
        id=export.id,
        created_at=export.created_at,
        updated_at=export.updated_at,
        exam_id=exam.id,
        exam_version_id=version.id,
        version_label=version.label,
        kind=export.kind,
        status=export.status,
        error=export.error,
        exam_revision=export.exam_revision,
        size_bytes=export.size_bytes,
        stale=export.exam_revision < exam.revision,
    )


def _all_mcq(db: Session, exam: Exam) -> bool:
    types = list(
        db.scalars(
            select(Question.type)
            .join(ExamItem, ExamItem.question_id == Question.id)
            .where(ExamItem.exam_id == exam.id)
        )
    )
    return bool(types) and all(t in CHOICE_TYPES for t in types)


def request(db: Session, user: User, exam_id: UUID, data: ExportsIn) -> ExportBatch:
    exam = exams_service.exam_for(db, user, exam_id)
    versions = list(
        db.scalars(
            select(ExamVersion).where(ExamVersion.exam_id == exam.id).order_by(ExamVersion.label)
        )
    )
    if data.versions != "all":
        wanted = set(data.versions)
        if wanted - {v.label for v in versions}:
            raise NotFound("version_not_found")
        versions = [v for v in versions if v.label in wanted]
    if not versions:
        raise Invalid("no_versions")
    kinds = list(dict.fromkeys(data.kinds))
    if "bubble_sheet_pdf" in kinds and not _all_mcq(db, exam):
        raise Invalid("bubble_sheet_requires_mcq")
    created = [
        Export(exam_version_id=v.id, kind=k, status="pending", exam_revision=exam.revision)
        for v in versions
        for k in kinds
    ]
    db.add_all(created)
    save(db)
    by_version = {v.id: v for v in versions}
    batch = ExportBatch(exports=[_out(e, by_version[e.exam_version_id], exam) for e in created])
    enqueue([e.id for e in created])
    return batch


def listing(db: Session, user: User, exam_id: UUID) -> list[ExportOut]:
    exam = exams_service.exam_for(db, user, exam_id)
    rows = db.execute(
        select(Export, ExamVersion)
        .join(ExamVersion, Export.exam_version_id == ExamVersion.id)
        .where(ExamVersion.exam_id == exam.id)
        .order_by(Export.created_at, Export.id)
    )
    return [_out(e, v, exam) for e, v in rows]


def _owned(db: Session, user: User, export_id: UUID) -> tuple[Export, ExamVersion, Exam]:
    export = found(db.get(Export, export_id))
    version = found(db.get(ExamVersion, export.exam_version_id))
    exam = exams_service.exam_for(db, user, version.exam_id)
    return export, version, exam


def download_name(exam: Exam, version: ExamVersion, kind: str) -> str:
    title = UNSAFE.sub(" ", exam.title).strip() or "exam"
    return f"{title}-{version.label}-{kind}.{extension(kind)}"


def content_disposition(filename: str) -> str:
    """RFC 6266 header with an ASCII fallback and the RFC 5987 UTF-8 name."""
    fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.encode("ascii", "ignore").decode())
    fallback = fallback.strip("_") or f"export.{filename.rpartition('.')[2] or 'pdf'}"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    try:
        while chunk := stream.read(CHUNK):
            yield chunk
    finally:
        stream.close()


def download(
    db: Session, user: User, export_id: UUID
) -> tuple[Iterator[bytes], str, int | None, str]:
    """The file stream, its Content-Disposition, its size and its media type."""
    export, version, exam = _owned(db, user, export_id)
    if export.status != "ready" or export.file_key is None:
        raise Conflict("export_not_ready")
    stream = get_store().open(export.file_key)
    return (
        _chunks(stream),
        content_disposition(download_name(exam, version, export.kind)),
        export.size_bytes,
        media_type(export.kind),
    )


def delete(db: Session, user: User, export_id: UUID) -> None:
    export, _, _ = _owned(db, user, export_id)
    key = export.file_key
    db.delete(export)
    save(db)
    if key:
        get_store().delete(key)


# --- worker side ------------------------------------------------------------------------------


def render_one(db: Session, export_id: UUID, store: ObjectStore | None = None) -> None:
    """Render one pending export; failures are recorded on the row, never raised."""
    store = store or get_store()
    export = db.get(Export, export_id)
    if export is None or export.status != "pending":
        return
    version = db.get(ExamVersion, export.exam_version_id)
    exam = db.get(Exam, version.exam_id) if version else None
    if version is None or exam is None:
        db.delete(export)
        db.commit()
        return
    revision = exam.revision
    try:
        data = render_export(db, exam, version, export.kind, store)
        key = keys.export(exam.org_id, export.id, extension(export.kind))
        store.put_bytes(key, data, media_type(export.kind))
    except Exception as exc:  # any failure must be recorded on the export row
        logger.warning("export_failed", export_id=str(export_id), error=str(exc))
        db.rollback()
        export = db.get(Export, export_id)
        if export is not None:
            export.status = "failed"
            export.error = str(exc)[:MAX_ERROR]
            db.commit()
        return
    export.exam_revision = revision
    export.file_key = key
    export.size_bytes = len(data)
    export.status = "ready"
    export.error = None
    superseded = list(
        db.scalars(
            select(Export).where(
                Export.exam_version_id == version.id,
                Export.kind == export.kind,
                Export.id != export.id,
                Export.status != "pending",
            )
        )
    )
    old_keys = [e.file_key for e in superseded if e.file_key]
    for old in superseded:
        db.delete(old)
    db.commit()
    for old_key in old_keys:
        store.delete(old_key)
