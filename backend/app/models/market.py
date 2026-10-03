import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class MarketInstrument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_instruments"
    __table_args__ = (UniqueConstraint("symbol", "exchange", name="uq_market_symbol_exchange"),)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    cik: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    registry_url: Mapped[str] = mapped_column(Text, nullable=False)
    registry_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DailyPrice(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("instrument_id", "session_date", name="uq_daily_price"),)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id"), nullable=False
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketFetchRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "market_fetch_runs"
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_instruments.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
