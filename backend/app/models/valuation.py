from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class ValuationObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "valuation_observations"
    __table_args__ = (
        UniqueConstraint("instrument_id", "fingerprint", name="uq_valuation_observation"),
    )
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("market_instruments.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
