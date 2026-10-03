"""Persist the authoritative SEC name/CIK/ticker snapshot."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261003_0008"
down_revision = "20261003_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entity_registries",
        sa.Column("name", sa.String(50), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("records", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("entity_registries")
