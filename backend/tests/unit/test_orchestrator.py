from uuid import uuid4

import pytest
from sqlalchemy import Select

from qbank.models import PageStatus, SourceStatus
from qbank.pipeline import orchestrator


def test_page_barrier_uses_stage_pending_status(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = [PageStatus.rendered]
    advanced: list[tuple[object, str]] = []

    class FakeSession:
        def __init__(self, engine: object) -> None:
            pass

        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def scalar(self, stmt: Select[object]) -> int:
            status = next(
                value for value in stmt.compile().params.values() if isinstance(value, PageStatus)
            )
            return pending.count(status)

    monkeypatch.setattr(orchestrator, "Session", FakeSession)
    monkeypatch.setattr(orchestrator, "get_engine", lambda: None)
    monkeypatch.setattr(
        orchestrator, "advance", lambda source, stage: advanced.append((source, stage))
    )
    monkeypatch.setattr(
        orchestrator,
        "STAGES",
        [
            orchestrator.Stage(
                "extract", lambda source: None, SourceStatus.extracting, PageStatus.rendered
            )
        ],
    )
    sid = uuid4()
    orchestrator.page_done(sid, "extract")
    assert not advanced
    pending.clear()
    orchestrator.page_done(sid, "extract")
    assert advanced == [(sid, "extract")]
