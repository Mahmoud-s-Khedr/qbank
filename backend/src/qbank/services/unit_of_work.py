from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qbank.services.errors import Conflict, NotFound


def save(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict() from None


def found[T](value: T | None) -> T:
    if value is None:
        raise NotFound()
    return value


def update(obj: object, values: BaseModel, *, exclude: set[str] | None = None) -> None:
    for key, value in values.model_dump(exclude_unset=True, exclude=exclude).items():
        setattr(obj, key, value)
