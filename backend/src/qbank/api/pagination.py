import base64
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, tuple_
from sqlalchemy.orm import Session

from qbank.models import ModelBase


def paginate[T: ModelBase](
    db: Session, stmt: Select[T], model: type[T], cursor: str | None, limit: int
) -> tuple[list[T], str | None]:
    if cursor:
        try:
            value = base64.urlsafe_b64decode(cursor.encode()).decode()
            date, identifier = value.split("|", 1)
            stmt = stmt.where(
                tuple_(model.created_at, model.id)
                > tuple_(datetime.fromisoformat(date), UUID(identifier))
            )
        except (ValueError, UnicodeError) as exc:
            raise ValueError("Invalid cursor") from exc
    rows = list(db.scalars(stmt.order_by(model.created_at, model.id).limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last: Any = rows[-1]
        next_cursor = base64.urlsafe_b64encode(
            f"{last.created_at.isoformat()}|{last.id}".encode()
        ).decode()
    return rows, next_cursor
