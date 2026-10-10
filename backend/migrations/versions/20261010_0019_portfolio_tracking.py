"""Immutable portfolio observations, sourced corporate actions and price mappings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261010_0019"
down_revision = "20261010_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "observation_date", "fingerprint", name="uq_portfolio_observation"
        ),
    )
    op.create_index(
        "ix_portfolio_observations_portfolio_id", "portfolio_observations", ["portfolio_id"]
    )
    op.create_table(
        "portfolio_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), sa.ForeignKey("paper_portfolios.id"), nullable=False),
        sa.Column(
            "instrument_id", sa.Uuid(), sa.ForeignKey("market_instruments.id"), nullable=False
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "instrument_id", "kind", "effective_date", name="uq_portfolio_action"
        ),
    )
    op.create_index("ix_portfolio_actions_portfolio_id", "portfolio_actions", ["portfolio_id"])
    op.create_table(
        "price_listing_mappings",
        sa.Column(
            "instrument_id", sa.Uuid(), sa.ForeignKey("market_instruments.id"), nullable=False
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id"),
    )


def downgrade():
    op.drop_table("price_listing_mappings")
    op.drop_table("portfolio_actions")
    op.drop_table("portfolio_observations")
