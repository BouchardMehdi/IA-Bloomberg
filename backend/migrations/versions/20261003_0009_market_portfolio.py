"""Daily market observations and a paper portfolio ledger."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261003_0009"
down_revision = "20261003_0008"
branch_labels = None
depends_on = None


def identity():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def timestamps():
    return [
        sa.Column(n, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
        for n in ("created_at", "updated_at")
    ]


def fk(name, table):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(f"{table}.id"), nullable=False)


def number(name, scale=2):
    return sa.Column(name, sa.Numeric(20, scale), nullable=False)


def upgrade() -> None:
    op.create_table(
        "market_instruments",
        identity(),
        *timestamps(),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("exchange", sa.String(50), nullable=False),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("registry_url", sa.Text(), nullable=False),
        sa.Column("registry_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "exchange", name="uq_market_symbol_exchange"),
    )
    op.create_table(
        "daily_prices",
        identity(),
        fk("instrument_id", "market_instruments"),
        sa.Column("session_date", sa.Date(), nullable=False),
        number("close", 6),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("instrument_id", "session_date", name="uq_daily_price"),
    )
    op.create_table(
        "market_fetch_runs",
        identity(),
        fk("instrument_id", "market_instruments"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(50)),
    )
    op.create_index("ix_market_fetch_runs_started_at", "market_fetch_runs", ["started_at"])
    op.create_table(
        "paper_portfolios",
        identity(),
        *timestamps(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        number("initial_capital"),
        number("cash"),
        sa.Column("fee_bps", sa.Numeric(8, 2), nullable=False),
        sa.Column("max_position_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("allowed_symbols", postgresql.JSONB(), nullable=False),
        sa.Column("starts_on", sa.Date()),
        sa.Column("ends_on", sa.Date()),
    )
    op.create_table(
        "paper_positions",
        identity(),
        fk("portfolio_id", "paper_portfolios"),
        fk("instrument_id", "market_instruments"),
        sa.Column("quantity", sa.Integer(), nullable=False),
        number("cost_basis"),
        sa.UniqueConstraint("portfolio_id", "instrument_id", name="uq_paper_position"),
    )
    op.create_table(
        "paper_trades",
        identity(),
        fk("portfolio_id", "paper_portfolios"),
        fk("instrument_id", "market_instruments"),
        sa.Column("client_order_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        number("price", 6),
        number("fee"),
        number("realized_pnl"),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("quote_source_url", sa.String(512), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("portfolio_id", "client_order_id", name="uq_paper_order"),
    )


def downgrade() -> None:
    for name in (
        "paper_trades",
        "paper_positions",
        "paper_portfolios",
        "market_fetch_runs",
        "daily_prices",
        "market_instruments",
    ):
        op.drop_table(name)
