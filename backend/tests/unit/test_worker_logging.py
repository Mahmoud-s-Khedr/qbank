import logging
from typing import Any
from uuid import uuid4

import dramatiq

from qbank.security.worker_logging import MessageLog, RedactDramatiq, configure_worker_logging


def test_worker_logs_outcome_without_message_payload(caplog: object) -> None:
    from _pytest.logging import LogCaptureFixture  # noqa: PLC0415

    assert isinstance(caplog, LogCaptureFixture)
    configure_worker_logging()
    source = str(uuid4())
    message: dramatiq.Message[Any] = dramatiq.Message(
        queue_name="default",
        actor_name="render_source",
        args=(source, "private-prompt"),
        kwargs={},
        options={},
    )
    middleware = MessageLog()
    with caplog.at_level(logging.INFO):
        middleware.before_process_message(None, message)  # type: ignore[arg-type]  # Broker unused.
        middleware.after_process_message(None, message, exception=ValueError("private-password"))  # type: ignore[arg-type]  # Broker unused.
    assert '"actor": "render_source"' in caplog.text
    assert source in caplog.text
    assert '"outcome": "error"' in caplog.text
    assert '"duration_ms":' in caplog.text
    assert "private-prompt" not in caplog.text
    assert "private-password" not in caplog.text


def test_dramatiq_failure_log_is_redacted() -> None:
    record = logging.LogRecord(
        "dramatiq.worker", logging.ERROR, __file__, 1, "failed: %s", ("private-prompt",), None
    )
    assert RedactDramatiq().filter(record)
    assert record.getMessage() == "dramatiq_event"


def test_worker_reads_source_from_failure_callback(caplog: object) -> None:
    from _pytest.logging import LogCaptureFixture  # noqa: PLC0415

    assert isinstance(caplog, LogCaptureFixture)
    source = str(uuid4())
    message: dramatiq.Message[Any] = dramatiq.Message(
        queue_name="default",
        actor_name="render_failed",
        args=({"args": [source], "private": "do-not-log"},),
        kwargs={},
        options={},
    )
    with caplog.at_level(logging.INFO):
        MessageLog().after_process_message(None, message)  # type: ignore[arg-type]  # Broker unused.
    assert source in caplog.text
    assert "do-not-log" not in caplog.text
