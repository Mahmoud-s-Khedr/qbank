from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

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

    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


class Lesson(ModelBase):
    __tablename__ = "lessons"
    chapter_id: Mapped[UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)

    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


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
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


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


class LLMCall(ModelBase):
    __tablename__ = "llm_calls"
    org_id: Mapped[UUID | None] = mapped_column(ForeignKey("organizations.id"))
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("sources.id"))
    stage: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str | None] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    reasoning_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9))
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), server_default=text("0"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    latency_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    error_code: Mapped[str | None] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String)


class Stimulus(ModelBase):
    __tablename__ = "stimuli"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    regions: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String, server_default=text("'draft'"))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )


class Question(ModelBase):
    __tablename__ = "questions"
    __table_args__ = (
        Index(
            "ix_questions_normalized_text_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
        Index(
            "ix_questions_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "ix_questions_tags_gin",
            "tags",
            postgresql_using="gin",
        ),
        Index(
            "ix_questions_org_subject_status",
            "org_id",
            "subject_id",
            "status",
        ),
        Index(
            "ix_questions_org_created_id",
            "org_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_questions_org_difficulty_id",
            "org_id",
            "difficulty",
            "id",
        ),
        Index(
            "ix_questions_org_source_order",
            "org_id",
            "source_id",
            "position",
            "id",
            postgresql_where=text("duplicate_of_id IS NULL"),
        ),
        Index(
            "ix_questions_facets",
            "org_id",
            "subject_id",
            "chapter_id",
            "lesson_id",
            "source_id",
            "type",
            "difficulty",
            "status",
            postgresql_where=text("duplicate_of_id IS NULL"),
        ),
    )
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id"), index=True)
    # Null for questions entered by hand (F5.4).
    source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[UUID | None] = mapped_column(ForeignKey("chapters.id"), index=True)
    lesson_id: Mapped[UUID | None] = mapped_column(ForeignKey("lessons.id"), index=True)
    stimulus_id: Mapped[UUID | None] = mapped_column(ForeignKey("stimuli.id"))
    stimulus_position: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    number_label: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    stem: Mapped[str] = mapped_column(String)
    choices: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    answer: Mapped[str | None] = mapped_column(String)
    explanation: Mapped[str | None] = mapped_column(String)
    difficulty: Mapped[int | None] = mapped_column(Integer)
    difficulty_reason: Mapped[str | None] = mapped_column(String)
    difficulty_source: Mapped[str | None] = mapped_column(String)
    taxonomy_source: Mapped[str | None] = mapped_column(String)
    answer_source: Mapped[str | None] = mapped_column(String)
    language: Mapped[Language] = mapped_column(Enum(Language, name="subject_language"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    regions: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String, server_default=text("'draft'"))
    confidence: Mapped[float] = mapped_column()
    normalized_text: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(normalized_text, ''))", persisted=True),
    )
    content_hash: Mapped[str | None] = mapped_column(String)
    duplicate_of_id: Mapped[UUID | None] = mapped_column(ForeignKey("questions.id"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    issues: Mapped[list["ValidationIssue"]] = relationship(
        "ValidationIssue",
        lazy="selectin",
        order_by="ValidationIssue.created_at, ValidationIssue.id",
        cascade="all, delete-orphan",
    )


class ValidationIssue(ModelBase):
    __tablename__ = "validation_issues"
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))


class QuestionEvent(ModelBase):
    __tablename__ = "question_events"
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String)
    diff: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class Asset(ModelBase):
    __tablename__ = "assets"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_page_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_pages.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String)
    image_key: Mapped[str] = mapped_column(String)
    pipeline_generated: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    region: Mapped[list[float]] = mapped_column(JSONB)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)


class PageProposal(ModelBase):
    """A re-extraction result awaiting review; it never touches live rows until accepted."""

    __tablename__ = "page_proposals"
    page_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_pages.id", ondelete="CASCADE"), index=True
    )
    extraction: Mapped[dict[str, object]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 9), server_default=text("0"))
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String, server_default=text("'pending'"))


class Exam(ModelBase):
    __tablename__ = "exams"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[UUID] = mapped_column(ForeignKey("subjects.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    settings: Mapped[dict[str, object]] = mapped_column(JSONB)
    blueprint: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String, server_default=text("'draft'"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class ExamProposal(ModelBase):
    __tablename__ = "exam_proposals"
    exam_id: Mapped[UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    plan: Mapped[dict[str, object]] = mapped_column(JSONB)
    selection: Mapped[dict[str, object]] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    status: Mapped[str] = mapped_column(String, server_default=text("'pending'"))


class ExamSection(ModelBase):
    __tablename__ = "exam_sections"
    exam_id: Mapped[UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)
    instructions: Mapped[str | None] = mapped_column(String)


class ExamItem(ModelBase):
    __tablename__ = "exam_items"
    __table_args__ = (UniqueConstraint("exam_id", "question_id"),)
    exam_id: Mapped[UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("exam_sections.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[UUID] = mapped_column(ForeignKey("questions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float, server_default=text("1"))
    origin: Mapped[str] = mapped_column(String, server_default=text("'manual'"))


class ExamVersion(ModelBase):
    __tablename__ = "exam_versions"
    __table_args__ = (UniqueConstraint("exam_id", "label"),)
    exam_id: Mapped[UUID] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String)
    seed: Mapped[int] = mapped_column(Integer)
    layout: Mapped[dict[str, object]] = mapped_column(JSONB)
    exam_revision: Mapped[int] = mapped_column(Integer)


class ExamTemplate(ModelBase):
    __tablename__ = "exam_templates"
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    header: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    logo_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"))


class Export(ModelBase):
    """A rendered file of one exam version. Staleness is computed: exam_revision < exam.revision."""

    __tablename__ = "exports"
    exam_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("exam_versions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, server_default=text("'pending'"))
    file_key: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String)
    exam_revision: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
