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
from qbank.storage import get_store, keys

dramatiq.set_broker(RedisBroker(url=get_settings().redis_url))  # type: ignore[no-untyped-call]  # Dramatiq lacks constructor types.


def fail_source(source_id: UUID, error: str) -> None:
    with Session(get_engine()) as db:
        db.execute(
            update(Source)
            .where(Source.id == source_id)
            .values(status=SourceStatus.failed, error=error)
        )
        db.execute(update(Job).where(Job.ref_id == source_id).values(status="failed", error=error))
        db.commit()


@dramatiq.actor(max_retries=3)
def render_source(source_id: str) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        if source is None or source.stage != "render":
            return
        file_key = source.file_key
    # Storage errors propagate to Dramatiq for retry.
    data = get_store().get_bytes(file_key)
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]  # PyMuPDF lacks constructor types.
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
    for number in pending:
        render_page.send(source_id, number)
    if not pending:
        page_done(sid, "render")


@dramatiq.actor(max_retries=3)
def render_page(source_id: str, page_number: int) -> None:
    sid = UUID(source_id)
    with Session(get_engine()) as db:
        source = db.get(Source, sid)
        page = db.scalar(
            select(SourcePage).where(
                SourcePage.source_id == sid, SourcePage.page_number == page_number
            )
        )
        if source is None or page is None or page.status != PageStatus.pending:
            return
        org, file_key = source.org_id, source.file_key
    data = get_store().get_bytes(file_key)
    settings = get_settings()
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:  # type: ignore[no-untyped-call]  # PyMuPDF lacks constructor types.
            pdf_page = document.load_page(page_number - 1)
            display = pdf_page.get_pixmap(dpi=settings.render_dpi_display, alpha=False)
            hires = pdf_page.get_pixmap(dpi=settings.render_dpi_hires, alpha=False)
            # Pillow supplies WebP encoding (PyMuPDF's support varies by version).
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
