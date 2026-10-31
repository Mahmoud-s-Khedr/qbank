"""Add LLM budget reservations and HTTP attempt counts."""

import sqlalchemy as sa
from alembic import op

revision = "cdef23456789"
down_revision = "bcde12345678"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("reserved_usd", sa.Numeric(18, 9), nullable=False, server_default="0"),
    )
    op.add_column(
        "llm_calls", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "attempts")
    op.drop_column("llm_calls", "reserved_usd")
