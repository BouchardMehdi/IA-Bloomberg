from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class PortfolioObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "portfolio_observations"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "observation_date", "fingerprint", name="uq_portfolio_observation"
        ),
    )
    portfolio_id: Mapped[UUID] = mapped_column(ForeignKey("paper_portfolios.id"), index=True)
    observation_date: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSONB)


class PortfolioAction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "portfolio_actions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "instrument_id", "kind", "effective_date", name="uq_portfolio_action"
        ),
    )
    portfolio_id: Mapped[UUID] = mapped_column(ForeignKey("paper_portfolios.id"), index=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("market_instruments.id"))
    kind: Mapped[str] = mapped_column(String(20))
    effective_date: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB)


class PriceListingMapping(Base):
    __tablename__ = "price_listing_mappings"
    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_instruments.id"), primary_key=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB)
