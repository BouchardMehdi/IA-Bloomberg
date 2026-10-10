"""Durable passage jobs for the outbound-only local AI worker."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261010_0022"
down_revision = "20261010_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ai_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_id", sa.Uuid()),
        sa.Column("result", JSONB()),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(80)))
    op.create_index("ix_ai_tasks_status", "ai_tasks", ["status"])
    op.create_table("ai_worker_state",
        sa.Column("name", sa.String(30), primary_key=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False))


def downgrade():
    op.drop_table("ai_worker_state")
    op.drop_table("ai_tasks")
