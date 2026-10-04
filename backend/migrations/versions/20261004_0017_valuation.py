"""Sourced valuation inputs tied to a security and quote session."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261004_0017"
down_revision = "20261004_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "valuation_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["instrument_id"], ["market_instruments.id"]),
        sa.UniqueConstraint("instrument_id", "fingerprint", name="uq_valuation_observation"),
    )
    op.create_index(
        "ix_valuation_observations_instrument_id", "valuation_observations", ["instrument_id"]
    )


def downgrade():
    op.drop_table("valuation_observations")
