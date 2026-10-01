"""Add structured event enrichment and companies.

Revision ID: 20261001_0004
Revises: 20260930_0003
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261001_0004"
down_revision: str | None = "20260930_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("extraction_method", sa.String(length=50)))
    op.add_column("events", sa.Column("extraction_version", sa.String(length=50)))
    op.add_column("events", sa.Column("evidence_excerpt", sa.Text()))
    op.add_column("events", sa.Column("structured_data", postgresql.JSONB()))

    op.create_table(
        "companies",
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cik"),
    )
    op.create_table(
        "event_companies",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="subject", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "company_id"),
    )


def downgrade() -> None:
    op.drop_table("event_companies")
    op.drop_table("companies")
    op.drop_column("events", "structured_data")
    op.drop_column("events", "evidence_excerpt")
    op.drop_column("events", "extraction_version")
    op.drop_column("events", "extraction_method")
