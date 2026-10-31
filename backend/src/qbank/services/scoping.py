from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from qbank.models import Chapter, Lesson, Question, Source, Subject, User

T = TypeVar("T", User, Subject, Chapter, Lesson, Question, Source)


def scoped[T: (User, Subject, Chapter, Lesson, Question, Source)](
    stmt: Select[T], model: type[T], org_id: UUID
) -> Select[T]:
    if model is Chapter:
        return stmt.join(Subject, Chapter.subject_id == Subject.id).where(Subject.org_id == org_id)
    if model is Lesson:
        return (
            stmt.join(Chapter, Lesson.chapter_id == Chapter.id)
            .join(Subject, Chapter.subject_id == Subject.id)
            .where(Subject.org_id == org_id)
        )
    if model is User:
        return stmt.where(User.org_id == org_id)
    if model is Question:
        return stmt.where(Question.org_id == org_id)
    if model is Source:
        return stmt.where(Source.org_id == org_id)
    return stmt.where(Subject.org_id == org_id)


def get[T: (User, Subject, Chapter, Lesson, Question, Source)](
    db: Session, model: type[T], org_id: UUID, resource_id: UUID
) -> T | None:
    return db.scalar(scoped(select(model), model, org_id).where(model.id == resource_id))
