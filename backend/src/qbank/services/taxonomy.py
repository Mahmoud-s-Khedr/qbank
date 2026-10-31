from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from qbank.api.pagination import paginate
from qbank.models import Chapter, Lesson, Source, Subject
from qbank.schemas.taxonomy import (
    ChapterOut,
    ItemIn,
    ItemUpdate,
    LessonUpdate,
    Reorder,
    SubjectIn,
    SubjectOut,
    SubjectUpdate,
)
from qbank.services.errors import Conflict, Invalid
from qbank.services.scoping import get, scoped
from qbank.services.unit_of_work import found, save, update


def ensure_deletable_subject(db: Session, org_id: UUID, subject_id: UUID) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Chapter)
            .join(Subject)
            .where(Subject.org_id == org_id, Chapter.subject_id == subject_id)
        )
        == 0
        and db.scalar(
            select(func.count())
            .select_from(Source)
            .where(Source.org_id == org_id, Source.subject_id == subject_id)
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


def next_position(
    db: Session, model: type[Chapter] | type[Lesson], parent_id: UUID, org_id: UUID
) -> int:
    if model is Chapter:
        stmt = (
            select(func.max(Chapter.position))
            .join(Subject)
            .where(Subject.org_id == org_id, Chapter.subject_id == parent_id)
        )
    else:
        stmt = (
            select(func.max(Lesson.position))
            .join(Chapter)
            .join(Subject)
            .where(Subject.org_id == org_id, Lesson.chapter_id == parent_id)
        )
    return (db.scalar(stmt) or 0) + 1


def subjects(
    db: Session, org_id: UUID, cursor: str | None = None, limit: int = 50
) -> dict[str, object]:
    try:
        items, next_cursor = paginate(
            db, scoped(select(Subject), Subject, org_id), Subject, cursor, limit
        )
    except ValueError:
        raise Invalid("invalid_cursor") from None
    return {"items": items, "next_cursor": next_cursor}


def create_subject(data: SubjectIn, db: Session, org_id: UUID) -> Subject:
    item = Subject(org_id=org_id, **data.model_dump())
    db.add(item)
    save(db)
    return item


def subject(id: UUID, db: Session, org_id: UUID) -> Subject:
    return found(get(db, Subject, org_id, id))


def edit_subject(id: UUID, data: SubjectUpdate, db: Session, org_id: UUID) -> Subject:
    item = found(get(db, Subject, org_id, id))
    update(item, data)
    save(db)
    return item


def delete_subject(id: UUID, db: Session, org_id: UUID) -> None:
    item = found(get(db, Subject, org_id, id))
    if not ensure_deletable_subject(db, org_id, id):
        raise Conflict("not_empty")
    db.delete(item)
    save(db)


def tree(id: UUID, db: Session, org_id: UUID) -> dict[str, object]:
    item = found(get(db, Subject, org_id, id))
    chapters = db.scalars(
        scoped(select(Chapter), Chapter, org_id)
        .where(Chapter.subject_id == id)
        .order_by(Chapter.position, Chapter.id)
    ).all()
    lessons = db.scalars(
        scoped(select(Lesson), Lesson, org_id)
        .where(Chapter.subject_id == id)
        .order_by(Lesson.position, Lesson.id)
    ).all()
    by_chapter: dict[UUID, list[Lesson]] = {chapter.id: [] for chapter in chapters}
    for lesson in lessons:
        by_chapter[lesson.chapter_id].append(lesson)
    return {
        **SubjectOut.model_validate(item).model_dump(),
        "chapters": [
            {**ChapterOut.model_validate(chapter).model_dump(), "lessons": by_chapter[chapter.id]}
            for chapter in chapters
        ],
    }


def create_chapter(id: UUID, data: ItemIn, db: Session, org_id: UUID) -> Chapter:
    found(get(db, Subject, org_id, id))
    item = Chapter(subject_id=id, title=data.title, position=next_position(db, Chapter, id, org_id))
    db.add(item)
    save(db)
    return item


def edit_chapter(id: UUID, data: ItemUpdate, db: Session, org_id: UUID) -> Chapter:
    item = found(get(db, Chapter, org_id, id))
    update(item, data)
    save(db)
    return item


def delete_chapter(id: UUID, db: Session, org_id: UUID) -> None:
    item = found(get(db, Chapter, org_id, id))
    if not ensure_deletable_chapter(db, org_id, id):
        raise Conflict("not_empty")
    db.delete(item)
    save(db)


def create_lesson(id: UUID, data: ItemIn, db: Session, org_id: UUID) -> Lesson:
    found(get(db, Chapter, org_id, id))
    item = Lesson(chapter_id=id, title=data.title, position=next_position(db, Lesson, id, org_id))
    db.add(item)
    save(db)
    return item


def edit_lesson(id: UUID, data: LessonUpdate, db: Session, org_id: UUID) -> Lesson:
    item = found(get(db, Lesson, org_id, id))
    if data.chapter_id is not None and data.chapter_id != item.chapter_id:
        target = found(get(db, Chapter, org_id, data.chapter_id))
        source = found(get(db, Chapter, org_id, item.chapter_id))
        if source.subject_id != target.subject_id:
            raise Invalid("invalid_move")
        data.position = next_position(db, Lesson, target.id, org_id)
    update(item, data)
    save(db)
    return item


def delete_lesson(id: UUID, db: Session, org_id: UUID) -> None:
    item = found(get(db, Lesson, org_id, id))
    db.delete(item)
    save(db)


def reorder_chapters(id: UUID, data: Reorder, db: Session, org_id: UUID) -> None:
    found(get(db, Subject, org_id, id))
    items = list(
        db.scalars(scoped(select(Chapter), Chapter, org_id).where(Chapter.subject_id == id))
    )
    if len(data.ids) != len(items) or set(data.ids) != {item.id for item in items}:
        raise Invalid("invalid_order")
    positions = {item_id: pos for pos, item_id in enumerate(data.ids, 1)}
    for item in items:
        item.position = positions[item.id]
    save(db)


def reorder_lessons(id: UUID, data: Reorder, db: Session, org_id: UUID) -> None:
    found(get(db, Chapter, org_id, id))
    items = list(db.scalars(scoped(select(Lesson), Lesson, org_id).where(Lesson.chapter_id == id)))
    if len(data.ids) != len(items) or set(data.ids) != {item.id for item in items}:
        raise Invalid("invalid_order")
    positions = {item_id: pos for pos, item_id in enumerate(data.ids, 1)}
    for item in items:
        item.position = positions[item.id]
    save(db)
