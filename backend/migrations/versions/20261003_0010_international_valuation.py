"""International listing identities and sourced USD conversions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261003_0010"
down_revision = "20261003_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("market_instruments", "cik", nullable=True)
    op.add_column("market_instruments", sa.Column("isin", sa.String(12)))
    op.add_column("market_instruments", sa.Column("identity_as_of", sa.Date()))
    op.create_unique_constraint(
        "uq_market_isin_exchange", "market_instruments", ["isin", "exchange"]
    )
    op.add_column("market_instruments", sa.Column("bloomberg_symbol", sa.String(100)))
    op.create_unique_constraint(
        "market_instruments_bloomberg_symbol_key", "market_instruments", ["bloomberg_symbol"]
    )
    op.add_column(
        "market_instruments",
        sa.Column("quote_multiplier", sa.Numeric(12, 6), nullable=False, server_default="1"),
    )
    op.add_column(
        "market_instruments",
        sa.Column("price_provider", sa.String(30), nullable=False, server_default="alpha_vantage"),
    )
    op.add_column("paper_trades", sa.Column("conversion", postgresql.JSONB()))
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("usd_per_unit", sa.Numeric(20, 10), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("currency", "rate_date", name="uq_fx_currency_date"),
    )


def downgrade():
    # Refuse to lose international identities or immutable conversion evidence.
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM market_instruments "
            "WHERE cik IS NULL OR price_provider != 'alpha_vantage')"
        )
    ):
        raise RuntimeError("Remove international instruments explicitly before downgrading.")
    if connection.scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM paper_trades WHERE conversion IS NOT NULL)")
    ):
        raise RuntimeError("Converted trades must retain their provenance.")
    op.drop_table("fx_rates")
    op.drop_column("paper_trades", "conversion")
    op.drop_column("market_instruments", "price_provider")
    op.drop_column("market_instruments", "quote_multiplier")
    op.drop_constraint(
        "market_instruments_bloomberg_symbol_key", "market_instruments", type_="unique"
    )
    op.drop_column("market_instruments", "bloomberg_symbol")
    op.drop_constraint("uq_market_isin_exchange", "market_instruments", type_="unique")
    op.drop_column("market_instruments", "identity_as_of")
    op.drop_column("market_instruments", "isin")
    op.alter_column("market_instruments", "cik", nullable=False)
