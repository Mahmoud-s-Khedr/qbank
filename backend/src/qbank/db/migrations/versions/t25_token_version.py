"""Revoke sessions after credential or privilege changes."""

import sqlalchemy as sa
from alembic import op

revision = "t25"
down_revision = "t16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
