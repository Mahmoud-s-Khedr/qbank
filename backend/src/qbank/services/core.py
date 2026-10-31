from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from qbank.models import Chapter, Lesson, Subject, User

T = TypeVar("T", User, Subject, Chapter, Lesson)


def scoped[T: (User, Subject, Chapter, Lesson)](
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
    return stmt.where(Subject.org_id == org_id)


def get[T: (User, Subject, Chapter, Lesson)](
    db: Session, model: type[T], org_id: UUID, resource_id: UUID
) -> T | None:
    return db.scalar(scoped(select(model), model, org_id).where(model.id == resource_id))


def ensure_deletable_subject(db: Session, org_id: UUID, subject_id: UUID) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Chapter)
            .join(Subject)
            .where(Subject.org_id == org_id, Chapter.subject_id == subject_id)
        )
        == 0
    )


def ensure_deletable_chapter(db: Session, org_id: UUID, chapter_id: UUID) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Lesson)
            .join(Chapter)
            .join(Subject)
            .where(Subject.org_id == org_id, Lesson.chapter_id == chapter_id)
        )
        == 0
    )
