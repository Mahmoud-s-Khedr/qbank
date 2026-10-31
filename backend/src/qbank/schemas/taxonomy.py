from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator

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
    # Accepting an AI-proposed node (T09) sends `proposed: false`; nodes can't be re-proposed.
    proposed: Literal[False] | None = None


class LessonUpdate(ItemUpdate):
    chapter_id: UUID | None = None


class ChapterOut(Output):
    subject_id: UUID
    title: str
    position: int
    # True for nodes the structure stage (T09) created as suggestions awaiting an editor.
    proposed: bool = Field(
        default=False, validation_alias=AliasChoices("metadata_json", "proposed")
    )

    @field_validator("proposed", mode="before")
    @classmethod
    def _proposed(cls, value: object) -> bool:
        if isinstance(value, dict):
            return value.get("proposed") is True
        return bool(value)


class LessonOut(Output):
    chapter_id: UUID
    title: str
    position: int
    # True for nodes the structure stage (T09) created as suggestions awaiting an editor.
    proposed: bool = Field(
        default=False, validation_alias=AliasChoices("metadata_json", "proposed")
    )

    @field_validator("proposed", mode="before")
    @classmethod
    def _proposed(cls, value: object) -> bool:
        if isinstance(value, dict):
            return value.get("proposed") is True
        return bool(value)


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
