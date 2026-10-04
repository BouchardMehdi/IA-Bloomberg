"""Append-only earnings provenance and shared provider request operations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261004_0013"
down_revision = "20261003_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "market_fetch_runs",
        sa.Column("operation", sa.String(30), nullable=False, server_default="prices"),
    )
    op.create_table(
        "earnings_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "instrument_id", sa.Uuid(), sa.ForeignKey("market_instruments.id"), nullable=False
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("instrument_id", "fingerprint", name="uq_earnings_observation"),
    )
    op.create_index(
        "ix_earnings_observations_instrument_id", "earnings_observations", ["instrument_id"]
    )


def downgrade():
    op.drop_table("earnings_observations")
    op.drop_column("market_fetch_runs", "operation")
