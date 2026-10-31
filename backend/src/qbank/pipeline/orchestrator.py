"""Atomic stage transitions and per-page completion barrier."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from qbank.db import get_engine
from qbank.models import Job, PageStatus, Source, SourcePage, SourceStatus


@dataclass(frozen=True)
class Stage:
    name: str
    start: Callable[[str], object]
    status: SourceStatus
    pending_status: PageStatus


def start_render(source_id: str) -> object:
    from qbank.worker import render_source  # noqa: PLC0415 -- avoids a worker import cycle.

    return render_source.send(source_id)


STAGES: list[Stage] = [Stage("render", start_render, SourceStatus.rendering, PageStatus.pending)]


def advance(source_id: UUID, finished_stage: str) -> bool:
    index = next(i for i, stage in enumerate(STAGES) if stage.name == finished_stage)
    next_stage = STAGES[index + 1] if index + 1 < len(STAGES) else None
    with Session(get_engine()) as db:
        winner = db.scalar(
            update(Source)
            .where(Source.id == source_id, Source.stage == finished_stage)
            .values(
                stage=next_stage.name if next_stage else None,
                status=next_stage.status if next_stage else SourceStatus.ready,
            )
            .returning(Source.id)
        )
        if winner and next_stage is None:
            db.execute(
                update(Job)
                .where(Job.ref_id == source_id, Job.kind == "ingest")
                .values(status="ready")
            )
        db.commit()
    if winner and next_stage:
        next_stage.start(str(source_id))
    return winner is not None


def page_done(source_id: UUID, stage: str) -> None:
    pending_status = next(item.pending_status for item in STAGES if item.name == stage)
    with Session(get_engine()) as db:
        remaining = db.scalar(
            select(func.count())
            .select_from(SourcePage)
            .where(SourcePage.source_id == source_id, SourcePage.status == pending_status)
        )
    if remaining == 0:
        advance(source_id, stage)
