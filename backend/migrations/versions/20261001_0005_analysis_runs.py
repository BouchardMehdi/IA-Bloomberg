"""Add semantic analysis run history.

Revision ID: 20261001_0005
Revises: 20261001_0004
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261001_0005"
down_revision: str | None = "20261001_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id",
            "model_name",
            "prompt_version",
            name="uq_analysis_runs_event_model_prompt",
        ),
    )
    op.create_index("ix_analysis_runs_event_id", "analysis_runs", ["event_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_status", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_event_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
