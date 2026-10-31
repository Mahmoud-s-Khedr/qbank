"""page proposals and manual questions

Revision ID: t12
Revises: t11
Create Date: 2026-10-31 19:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t12"
down_revision = "t11"  # the orchestrator re-parents this at merge
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("questions", "source_id", existing_type=sa.Uuid(), nullable=True)
    op.create_table(
        "page_proposals",
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("extraction", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 9), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_page_proposals_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["source_pages.id"],
            name=op.f("fk_page_proposals_page_id_source_pages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_proposals")),
    )
    op.create_index(op.f("ix_page_proposals_page_id"), "page_proposals", ["page_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_page_proposals_page_id"), table_name="page_proposals")
    op.drop_table("page_proposals")
    op.execute("DELETE FROM questions WHERE source_id IS NULL")
    op.alter_column("questions", "source_id", existing_type=sa.Uuid(), nullable=False)
