"""Track passage coverage and multiple sourced facts per publication."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261003_0007"
down_revision: str | None = "20261003_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("coverage", postgresql.JSONB()))
    op.add_column("events", sa.Column("parent_event_id", sa.Uuid()))
    op.add_column("events", sa.Column("fact_analysis_run_id", sa.Uuid()))
    op.create_foreign_key("fk_events_parent", "events", "events", ["parent_event_id"], ["id"])
    op.create_foreign_key(
        "fk_events_fact_run", "events", "analysis_runs", ["fact_analysis_run_id"], ["id"]
    )
    op.create_index("ix_events_parent_event_id", "events", ["parent_event_id"])
    op.create_table(
        "analysis_passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("run_id", "passage_index", name="uq_analysis_passages_run_index"),
    )
    op.create_index("ix_analysis_passages_run_id", "analysis_passages", ["run_id"])


def downgrade() -> None:
    op.drop_table("analysis_passages")
    op.drop_index("ix_events_parent_event_id", table_name="events")
    op.drop_constraint("fk_events_fact_run", "events", type_="foreignkey")
    op.drop_constraint("fk_events_parent", "events", type_="foreignkey")
    op.drop_column("events", "fact_analysis_run_id")
    op.drop_column("events", "parent_event_id")
    op.drop_column("analysis_runs", "coverage")
