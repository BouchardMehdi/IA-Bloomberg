"""Add document retrieval, event grouping and versioned analysis inputs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_0006"
down_revision: str | None = "20261001_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in [
        sa.Column("full_content", sa.Text()),
        sa.Column("full_content_hash", sa.String(64)),
        sa.Column("document_url", sa.String(2048)),
        sa.Column("content_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("content_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("content_next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("content_error", sa.Text()),
        sa.Column("content_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]:
        op.add_column("articles", column)
    op.create_index("ix_articles_full_content_hash", "articles", ["full_content_hash"])
    op.add_column("events", sa.Column("merged_into_event_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_events_merged_into", "events", "events", ["merged_into_event_id"], ["id"]
    )
    op.add_column("analysis_runs", sa.Column("input_text", sa.Text()))
    op.add_column("analysis_runs", sa.Column("source_url", sa.String(2048)))
    op.drop_constraint("uq_analysis_runs_event_model_prompt", "analysis_runs", type_="unique")
    op.create_unique_constraint(
        "uq_analysis_runs_event_model_prompt",
        "analysis_runs",
        ["event_id", "model_name", "prompt_version", "input_hash"],
    )


def downgrade() -> None:
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM analysis_runs GROUP BY event_id, model_name, prompt_version "
                "HAVING count(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicates:
        raise RuntimeError("Multiple analysis inputs exist: export history before downgrading")
    op.drop_constraint("uq_analysis_runs_event_model_prompt", "analysis_runs", type_="unique")
    op.create_unique_constraint(
        "uq_analysis_runs_event_model_prompt",
        "analysis_runs",
        ["event_id", "model_name", "prompt_version"],
    )
    op.drop_column("analysis_runs", "source_url")
    op.drop_column("analysis_runs", "input_text")
    op.drop_constraint("fk_events_merged_into", "events", type_="foreignkey")
    op.drop_column("events", "merged_into_event_id")
    op.drop_index("ix_articles_full_content_hash", "articles")
    for name in [
        "full_content",
        "full_content_hash",
        "document_url",
        "content_status",
        "content_attempts",
        "content_fetched_at",
        "content_next_retry_at",
        "content_error",
        "content_truncated",
    ]:
        op.drop_column("articles", name)
