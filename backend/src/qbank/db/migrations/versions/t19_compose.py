"""AI exam proposals."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t19"
down_revision = "t12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_proposals",
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("selection", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["exam_id"],
            ["exams.id"],
            name=op.f("fk_exam_proposals_exam_id_exams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_exam_proposals_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exam_proposals")),
    )
    op.create_index(op.f("ix_exam_proposals_exam_id"), "exam_proposals", ["exam_id"])
    op.create_index(op.f("ix_exam_proposals_user_id"), "exam_proposals", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_exam_proposals_user_id"), table_name="exam_proposals")
    op.drop_index(op.f("ix_exam_proposals_exam_id"), table_name="exam_proposals")
    op.drop_table("exam_proposals")
