from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class FinancialFact(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "financial_facts"
    __table_args__ = (UniqueConstraint("cik", "fingerprint", name="uq_financial_fact"),)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    period_end: Mapped[date] = mapped_column(Date, index=True)
    filed_on: Mapped[date] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB)
