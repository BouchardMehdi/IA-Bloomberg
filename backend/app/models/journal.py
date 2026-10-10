"""Append-only, authored research decisions; never an order instruction."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class ResearchDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "research_decisions"
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("market_instruments.id"), index=True)
    portfolio_id: Mapped[UUID | None] = mapped_column(ForeignKey("paper_portfolios.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRevision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "decision_revisions"
    __table_args__ = (UniqueConstraint("decision_id", "version"),)
    decision_id: Mapped[UUID] = mapped_column(ForeignKey("research_decisions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    client_request_id: Mapped[UUID] = mapped_column(unique=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    author: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
