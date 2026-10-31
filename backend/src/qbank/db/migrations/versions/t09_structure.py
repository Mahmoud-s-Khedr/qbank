"""Structure proposals and question provenance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t09"
down_revision = "t19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("chapters", "lessons", "sources"):
        op.add_column(
            table,
            sa.Column(
                "metadata",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    for name in ("taxonomy_source", "answer_source"):
        op.add_column("questions", sa.Column(name, sa.String(), nullable=True))


def downgrade() -> None:
    for name in ("answer_source", "taxonomy_source"):
        op.drop_column("questions", name)
    for table in ("sources", "lessons", "chapters"):
        op.drop_column(table, "metadata")
