import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class PaperPortfolio(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_portfolios"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    fee_bps: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    max_position_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    allowed_symbols: Mapped[list] = mapped_column(JSONB, nullable=False)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    wls_policy: Mapped[str] = mapped_column(
        String(30), nullable=False, default="verified", server_default="verified"
    )


class PaperPosition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "paper_positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "instrument_id", name="uq_paper_position"),)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_portfolios.id"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)


class PaperTrade(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "paper_trades"
    __table_args__ = (UniqueConstraint("portfolio_id", "client_order_id", name="uq_paper_order"),)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_portfolios.id"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id"), nullable=False
    )
    client_order_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    quote_date: Mapped[date] = mapped_column(Date, nullable=False)
    quote_source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversion: Mapped[dict | None] = mapped_column(JSONB)
    universe_evidence: Mapped[dict | None] = mapped_column(JSONB)
