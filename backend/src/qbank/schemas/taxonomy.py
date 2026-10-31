from uuid import UUID

from pydantic import BaseModel

from qbank.models import Language
from qbank.schemas.common import Output


class SubjectIn(BaseModel):
    name: str
    language: Language
    grade: str | None = None


class SubjectUpdate(BaseModel):
    name: str | None = None
    language: Language | None = None
    grade: str | None = None


class SubjectOut(Output, SubjectIn):
    org_id: UUID


class ItemIn(BaseModel):
    title: str


class ItemUpdate(BaseModel):
    title: str | None = None
    position: int | None = None


class LessonUpdate(ItemUpdate):
    chapter_id: UUID | None = None


class ChapterOut(Output):
    subject_id: UUID
    title: str
    position: int


class LessonOut(Output):
    chapter_id: UUID
    title: str
    position: int


class ChapterTree(ChapterOut):
    lessons: list[LessonOut]


class SubjectTree(SubjectOut):
    chapters: list[ChapterTree]


class Reorder(BaseModel):
    ids: list[UUID]


class ChapterMerge(BaseModel):
    into_chapter_id: UUID


class LessonMerge(BaseModel):
    into_lesson_id: UUID
