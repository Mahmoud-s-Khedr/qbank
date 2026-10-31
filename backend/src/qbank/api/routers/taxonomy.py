from uuid import UUID

from fastapi import APIRouter, Query

from qbank.api.deps import DB, Current, Writer
from qbank.models import Chapter, Lesson, Subject
from qbank.schemas.common import Page
from qbank.schemas.taxonomy import (
    ChapterOut,
    ItemIn,
    ItemUpdate,
    LessonOut,
    LessonUpdate,
    Reorder,
    SubjectIn,
    SubjectOut,
    SubjectTree,
    SubjectUpdate,
)
from qbank.services import taxonomy as service

router = APIRouter(prefix="/api/v1")


@router.get("/subjects", response_model=Page[SubjectOut])
def subjects(
    db: DB, user: Current, cursor: str | None = None, limit: int = Query(50, ge=1, le=100)
) -> dict[str, object]:
    return service.subjects(db=db, org_id=user.org_id, cursor=cursor, limit=limit)


@router.post("/subjects", response_model=SubjectOut, status_code=201)
def create_subject(data: SubjectIn, db: DB, user: Writer) -> Subject:
    return service.create_subject(data=data, db=db, org_id=user.org_id)


@router.get("/subjects/{id}", response_model=SubjectOut)
def subject(id: UUID, db: DB, user: Current) -> Subject:
    return service.subject(id=id, db=db, org_id=user.org_id)


@router.patch("/subjects/{id}", response_model=SubjectOut)
def edit_subject(id: UUID, data: SubjectUpdate, db: DB, user: Writer) -> Subject:
    return service.edit_subject(id=id, data=data, db=db, org_id=user.org_id)


@router.delete("/subjects/{id}", status_code=204)
def delete_subject(id: UUID, db: DB, user: Writer) -> None:
    service.delete_subject(id=id, db=db, org_id=user.org_id)


@router.get("/subjects/{id}/tree", response_model=SubjectTree)
def tree(id: UUID, db: DB, user: Current) -> dict[str, object]:
    return service.tree(id=id, db=db, org_id=user.org_id)


@router.post("/subjects/{id}/chapters", response_model=ChapterOut, status_code=201)
def create_chapter(id: UUID, data: ItemIn, db: DB, user: Writer) -> Chapter:
    return service.create_chapter(id=id, data=data, db=db, org_id=user.org_id)


@router.patch("/chapters/{id}", response_model=ChapterOut)
def edit_chapter(id: UUID, data: ItemUpdate, db: DB, user: Writer) -> Chapter:
    return service.edit_chapter(id=id, data=data, db=db, org_id=user.org_id)


@router.delete("/chapters/{id}", status_code=204)
def delete_chapter(id: UUID, db: DB, user: Writer) -> None:
    service.delete_chapter(id=id, db=db, org_id=user.org_id)


@router.post("/chapters/{id}/lessons", response_model=LessonOut, status_code=201)
def create_lesson(id: UUID, data: ItemIn, db: DB, user: Writer) -> Lesson:
    return service.create_lesson(id=id, data=data, db=db, org_id=user.org_id)


@router.patch("/lessons/{id}", response_model=LessonOut)
def edit_lesson(id: UUID, data: LessonUpdate, db: DB, user: Writer) -> Lesson:
    return service.edit_lesson(id=id, data=data, db=db, org_id=user.org_id)


@router.delete("/lessons/{id}", status_code=204)
def delete_lesson(id: UUID, db: DB, user: Writer) -> None:
    service.delete_lesson(id=id, db=db, org_id=user.org_id)


@router.post("/subjects/{id}/chapters/reorder", status_code=204)
def reorder_chapters(id: UUID, data: Reorder, db: DB, user: Writer) -> None:
    service.reorder_chapters(id=id, data=data, db=db, org_id=user.org_id)


@router.post("/chapters/{id}/lessons/reorder", status_code=204)
def reorder_lessons(id: UUID, data: Reorder, db: DB, user: Writer) -> None:
    service.reorder_lessons(id=id, data=data, db=db, org_id=user.org_id)
