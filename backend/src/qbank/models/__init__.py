from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from qbank.db import Base, Timestamps, UUIDPk


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
        return value.strip().lower()


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
