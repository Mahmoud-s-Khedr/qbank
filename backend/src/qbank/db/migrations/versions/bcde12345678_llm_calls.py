"""Add the LLM call ledger."""

import sqlalchemy as sa
from alembic import op

revision = "bcde12345678"
down_revision = "84bfb9035f01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(18, 9), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("request_hash", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
