"""Log message outcomes without serializing message bodies or exceptions."""

import logging
import threading
import time
from typing import Any
from uuid import UUID

import structlog
from dramatiq.broker import Broker, MessageProxy
from dramatiq.middleware import Middleware

from qbank.config import get_settings


class RedactDramatiq(logging.Filter):
    """Dramatiq's default failures include message arguments and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("dramatiq"):
            record.msg = "dramatiq_event"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True


def configure_worker_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(level=get_settings().log_level)
    logging.getLogger().setLevel(get_settings().log_level)
    for handler in logging.getLogger().handlers:
        if not any(isinstance(item, RedactDramatiq) for item in handler.filters):
            handler.addFilter(RedactDramatiq())


class MessageLog(Middleware):
    def __init__(self) -> None:
        self.started: dict[str, float] = {}
        self.lock = threading.Lock()

    def before_process_message(self, broker: Broker, message: MessageProxy) -> None:
        with self.lock:
            self.started[message.message_id] = time.monotonic()

    def after_process_message(
        self,
        broker: Broker,
        message: MessageProxy,
        *,
        result: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        with self.lock:
            start = self.started.pop(message.message_id, time.monotonic())
        source_id = None
        if message.actor_name == "reextract_page":
            index = 1
        elif message.actor_name.endswith(("_source", "_pages")):
            index = 0
        else:
            index = -1
        try:
            candidate = message.kwargs.get("source_id")
            if candidate is None and message.actor_name.endswith("_failed"):
                original = message.args[0]
                if isinstance(original, dict):
                    original_args = original.get("args", ())
                    if isinstance(original_args, (list, tuple)) and original_args:
                        candidate = original_args[0]
            if candidate is None and index >= 0:
                candidate = message.args[index]
            if candidate is not None:
                source_id = str(UUID(str(candidate)))
        except (ValueError, IndexError, TypeError, KeyError):
            pass
        structlog.get_logger().info(
            "worker_message",
            actor=message.actor_name,
            source_id=source_id,
            duration_ms=round((time.monotonic() - start) * 1000, 2),
            outcome="error" if exception else "ok",
        )
