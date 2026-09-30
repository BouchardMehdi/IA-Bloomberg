"""Create collection run history.

Revision ID: 20260930_0002
Revises: 20260930_0001
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260930_0002"
down_revision: str | None = "20260930_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_runs",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("inserted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collection_runs_source_id", "collection_runs", ["source_id"])
    op.create_index("ix_collection_runs_status", "collection_runs", ["status"])
    op.create_index(
        "ix_collection_runs_source_started",
        "collection_runs",
        ["source_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_runs_source_started", table_name="collection_runs")
    op.drop_index("ix_collection_runs_status", table_name="collection_runs")
    op.drop_index("ix_collection_runs_source_id", table_name="collection_runs")
    op.drop_table("collection_runs")
