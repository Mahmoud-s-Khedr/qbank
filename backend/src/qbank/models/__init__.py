from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from qbank.db import Base, Timestamps, UUIDPk


def normalize_email(value: str) -> str:
    return value.strip().lower()


class Role(StrEnum):
    admin = "admin"
    editor = "editor"
    teacher = "teacher"


class Language(StrEnum):
    ar = "ar"
    en = "en"


class ModelBase(UUIDPk, Timestamps, Base):
    __abstract__ = True


class Organization(ModelBase):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String, nullable=False)
    settings: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class User(ModelBase):
    __tablename__ = "users"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        return normalize_email(value)


class Subject(ModelBase):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint("org_id", "name", "grade", postgresql_nulls_not_distinct=True),
    )
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    language: Mapped[Language] = mapped_column(Enum(Language, name="subject_language"))
    grade: Mapped[str | None] = mapped_column(String)


class Chapter(ModelBase):
    __tablename__ = "chapters"
    subject_id: Mapped[UUID] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)


class Lesson(ModelBase):
    __tablename__ = "lessons"
    chapter_id: Mapped[UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)


class SourceStatus(StrEnum):
    uploaded = "uploaded"
    rendering = "rendering"
    extracting = "extracting"
    validating = "validating"
    ready = "ready"
    failed = "failed"
    paused = "paused"


class PageStatus(StrEnum):
    pending = "pending"
    rendered = "rendered"
    extracted = "extracted"
    validated = "validated"
    failed = "failed"


class PageKind(StrEnum):
    cover = "cover"
    blank = "blank"
    toc = "toc"
    section_divider = "section_divider"
    questions = "questions"
    answer_key = "answer_key"
    answer_sheet = "answer_sheet"
    other = "other"


class Source(ModelBase):
    __tablename__ = "sources"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    grade: Mapped[str | None] = mapped_column(String)
    file_key: Mapped[str] = mapped_column(String)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[SourceStatus] = mapped_column(Enum(SourceStatus, name="source_status"))
    stage: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    pipeline_config: Mapped[dict[str, object]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    cost_usd: Mapped[float] = mapped_column(server_default=text("0"))


class SourcePage(ModelBase):
    __tablename__ = "source_pages"
    __table_args__ = (UniqueConstraint("source_id", "page_number"),)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    page_kind: Mapped[PageKind | None] = mapped_column(Enum(PageKind, name="page_kind"))
    image_key: Mapped[str | None] = mapped_column(String)
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    dpi: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[PageStatus] = mapped_column(Enum(PageStatus, name="page_status"))
    error: Mapped[str | None] = mapped_column(String)
    extraction: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    prompt_version: Mapped[str | None] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    cost_usd: Mapped[float] = mapped_column(server_default=text("0"))


class Job(ModelBase):
    __tablename__ = "jobs"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    progress: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(String)
    ref_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
