"""Provider quotas, retries and explicit price conventions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261003_0012"
down_revision = "20261003_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "market_fetch_runs",
        sa.Column("provider", sa.String(30), nullable=False, server_default="alpha_vantage"),
    )
    op.add_column("market_fetch_runs", sa.Column("retry_at", sa.DateTime(timezone=True)))
    op.add_column("market_fetch_runs", sa.Column("quote_context", postgresql.JSONB()))
    op.create_index("ix_market_fetch_runs_provider", "market_fetch_runs", ["provider"])
    op.add_column(
        "daily_prices",
        sa.Column("provider", sa.String(30), nullable=False, server_default="manual"),
    )
    op.add_column("daily_prices", sa.Column("quote_context", postgresql.JSONB()))
    op.execute(
        "UPDATE daily_prices AS p SET provider = i.price_provider "
        "FROM market_instruments AS i WHERE i.id = p.instrument_id"
    )
    # Legacy observations keep null context: never invent a historical mapping proof.


def downgrade():
    op.drop_column("daily_prices", "quote_context")
    op.drop_column("daily_prices", "provider")
    op.drop_index("ix_market_fetch_runs_provider", table_name="market_fetch_runs")
    op.drop_column("market_fetch_runs", "quote_context")
    op.drop_column("market_fetch_runs", "retry_at")
    op.drop_column("market_fetch_runs", "provider")
