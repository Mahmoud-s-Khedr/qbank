"""Dramatiq render actors."""

from io import BytesIO
from uuid import UUID

import dramatiq
import pymupdf
from dramatiq.brokers.redis import RedisBroker
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from qbank.config import get_settings
from qbank.db import get_engine
from qbank.models import Job, PageStatus, Source, SourcePage, SourceStatus
from qbank.pipeline.orchestrator import page_done
from qbank.pipeline.pdf_cache import get_pdf_cache
from qbank.storage import get_store, keys

dramatiq.set_broker(RedisBroker(url=get_settings().redis_url))  # type: ignore[no-untyped-call]  # Dramatiq lacks constructor types.


def fail_source(source_id: UUID, error: str) -> None:
    with Session(get_engine()) as db:
        failed = db.scalar(
            update(Source)
            .where(
                Source.id == source_id,
                Source.stage == "render",
                Source.status == SourceStatus.rendering,
            )
            .values(status=SourceStatus.failed, error=error)
            .returning(Source.id)
        )
        if failed:
            db.execute(
                update(Job).where(Job.ref_id == source_id).values(status="failed", error=error)
            )
        db.commit()


@dramatiq.actor(max_retries=3)
def source_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    fail_source(UUID(str(args[0])), "storage_error: retries exhausted")


@dramatiq.actor(max_retries=3, on_retry_exhausted="source_failed")
def render_source(source_id: str) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "render":
            return
        file_key = source.file_key
    # Storage errors propagate to Dramatiq for retry.
    with get_pdf_cache().acquire(file_key, get_store()) as path:
        try:
            with pymupdf.open(str(path)) as document:  # type: ignore[no-untyped-call]  # PyMuPDF constructor is untyped.
                count = document.page_count
        except Exception as exc:
            fail_source(sid, str(exc))
            return
    if count > get_settings().max_pages:
        fail_source(sid, "too_many_pages")
        return
    with Session(get_engine()) as db:
        source = db.scalar(select(Source).where(Source.id == sid).with_for_update())
        if source is None or source.stage != "render":
            return
        source.page_count = count
        existing = set(
            db.scalars(select(SourcePage.page_number).where(SourcePage.source_id == sid))
        )
        for number in range(1, count + 1):
            if number not in existing:
                db.add(SourcePage(source_id=sid, page_number=number, status=PageStatus.pending))
        db.commit()
        pending = list(
            db.scalars(
                select(SourcePage.page_number).where(
                    SourcePage.source_id == sid, SourcePage.status == PageStatus.pending
                )
            )
        )
    batch_size = get_settings().render_batch_size
    for offset in range(0, len(pending), batch_size):
        render_pages.send(source_id, pending[offset : offset + batch_size])
    if not pending:
        page_done(sid, "render")


@dramatiq.actor(max_retries=3)
def render_failed(message: dict[str, object], details: dict[str, object]) -> None:
    args = message["args"]
    if not isinstance(args, (list, tuple)):
        raise ValueError("Invalid message arguments")
    sid = UUID(str(args[0]))
    numbers = args[1]
    if not isinstance(numbers, (list, tuple)):
        raise ValueError("Invalid page numbers")
    options = message.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("Invalid message options")
    trace = str(options.get("traceback", "storage failure")).strip().splitlines()[-1]
    with Session(get_engine()) as db:
        db.execute(
            update(SourcePage)
            .where(
                SourcePage.source_id == sid,
                SourcePage.page_number.in_(numbers),
                SourcePage.status == PageStatus.pending,
            )
            .values(status=PageStatus.failed, error=f"storage_error: {trace}")
        )
        db.commit()
    page_done(sid, "render")


@dramatiq.actor(max_retries=3, on_retry_exhausted="render_failed")
def render_pages(source_id: str, numbers: list[int]) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "render":
            return
        org, file_key = source.org_id, source.file_key
    with (
        get_pdf_cache().acquire(file_key, get_store()) as path,
        pymupdf.open(str(path)) as document,  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
    ):
        for number in numbers:
            render_one(sid, org, number, document)


def render_one(sid: UUID, org: UUID, page_number: int, document: pymupdf.Document) -> None:
    with Session(get_engine()) as db:
        page = db.scalar(
            select(SourcePage).where(
                SourcePage.source_id == sid, SourcePage.page_number == page_number
            )
        )
        if page is None or page.status != PageStatus.pending:
            return
    settings = get_settings()
    try:
        pdf_page = document.load_page(page_number - 1)  # type: ignore[no-untyped-call]  # PyMuPDF is untyped.
        display = pdf_page.get_pixmap(dpi=settings.render_dpi_display, alpha=False)
        hires = pdf_page.get_pixmap(dpi=settings.render_dpi_hires, alpha=False)
        image = Image.frombytes("RGB", (display.width, display.height), display.samples)
        output = BytesIO()
        image.save(output, format="WEBP")
        display_data = output.getvalue()
        hires_data = hires.tobytes("png")
    except Exception as exc:
        with Session(get_engine()) as db:
            db.execute(
                update(SourcePage)
                .where(
                    SourcePage.source_id == sid,
                    SourcePage.page_number == page_number,
                    SourcePage.status == PageStatus.pending,
                )
                .values(status=PageStatus.failed, error=str(exc))
            )
            db.commit()
        page_done(sid, "render")
        return
    display_key = keys.page(org, sid, page_number)
    get_store().put_bytes(display_key, display_data, "image/webp")
    get_store().put_bytes(keys.page(org, sid, page_number, hires=True), hires_data, "image/png")
    with Session(get_engine()) as db:
        db.execute(
            update(SourcePage)
            .where(
                SourcePage.source_id == sid,
                SourcePage.page_number == page_number,
                SourcePage.status == PageStatus.pending,
            )
            .values(
                status=PageStatus.rendered,
                image_key=display_key,
                width_px=display.width,
                height_px=display.height,
                dpi=settings.render_dpi_display,
            )
        )
        db.commit()
    page_done(sid, "render")


if __name__ == "__main__":
    import sys

    from dramatiq.cli import main

    sys.argv = ["dramatiq", "qbank.worker"]
    main()  # type: ignore[no-untyped-call]  # Dramatiq CLI is untyped.
