"""question bank search_vector and search/filter indexes

Revision ID: t16
Revises: t11
Create Date: 2026-10-31 18:05:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t16"
down_revision = "t11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(normalized_text, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_questions_search_vector",
        "questions",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_questions_tags_gin",
        "questions",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_questions_org_subject_status",
        "questions",
        ["org_id", "subject_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_questions_org_created_id",
        "questions",
        ["org_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_questions_org_difficulty_id",
        "questions",
        ["org_id", "difficulty", "id"],
        unique=False,
    )
    op.create_index(
        "ix_questions_org_source_order",
        "questions",
        ["org_id", "source_id", "position", "id"],
        unique=False,
        postgresql_where=sa.text("duplicate_of_id IS NULL"),
    )
    op.create_index(
        "ix_questions_facets",
        "questions",
        [
            "org_id",
            "subject_id",
            "chapter_id",
            "lesson_id",
            "source_id",
            "type",
            "difficulty",
            "status",
        ],
        unique=False,
        postgresql_where=sa.text("duplicate_of_id IS NULL"),
    )
    op.create_index(
        op.f("ix_questions_chapter_id"),
        "questions",
        ["chapter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_questions_lesson_id"),
        "questions",
        ["lesson_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_questions_lesson_id"), table_name="questions", if_exists=True)
    op.drop_index(op.f("ix_questions_chapter_id"), table_name="questions", if_exists=True)
    op.drop_index(
        "ix_questions_facets",
        table_name="questions",
        if_exists=True,
    )
    op.drop_index(
        "ix_questions_org_source_order",
        table_name="questions",
        if_exists=True,
    )
    op.drop_index("ix_questions_org_difficulty_id", table_name="questions", if_exists=True)
    op.drop_index("ix_questions_org_created_id", table_name="questions", if_exists=True)
    op.drop_index("ix_questions_org_subject_status", table_name="questions", if_exists=True)
    op.drop_index(
        "ix_questions_tags_gin",
        table_name="questions",
        postgresql_using="gin",
        if_exists=True,
    )
    op.drop_index(
        "ix_questions_search_vector",
        table_name="questions",
        postgresql_using="gin",
        if_exists=True,
    )
    op.drop_column("questions", "search_vector")
