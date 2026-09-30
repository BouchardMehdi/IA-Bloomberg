"""Add a stable event deduplication key.

Revision ID: 20260930_0003
Revises: 20260930_0002
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_0003"
down_revision: str | None = "20260930_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("deduplication_key", sa.String(length=255), nullable=True))
    op.execute("UPDATE events SET deduplication_key = 'legacy:' || id::text")
    op.alter_column("events", "deduplication_key", nullable=False)
    op.create_unique_constraint(
        "uq_events_deduplication_key",
        "events",
        ["deduplication_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_events_deduplication_key", "events", type_="unique")
    op.drop_column("events", "deduplication_key")
