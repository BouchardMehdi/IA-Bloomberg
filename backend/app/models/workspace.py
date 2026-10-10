"""Shared workspace access, immutable alerts and declared research metadata."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class WorkspaceUser(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workspace_users"
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkspaceSession(Base):
    __tablename__ = "workspace_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("workspace_users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class WorkspaceAlert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workspace_alerts"
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    instrument_id: Mapped[UUID | None] = mapped_column(ForeignKey("market_instruments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AlertReceipt(Base):
    __tablename__ = "alert_receipts"
    reader: Mapped[str] = mapped_column(String(80), primary_key=True)
    alert_id: Mapped[UUID] = mapped_column(ForeignKey("workspace_alerts.id"), primary_key=True)


class WorkspaceCursor(Base):
    __tablename__ = "workspace_cursors"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class InstrumentProfile(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "instrument_profiles"
    __table_args__ = (UniqueConstraint("instrument_id", "fingerprint"),)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("market_instruments.id"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class BenchmarkPoint(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "benchmark_points"
    __table_args__ = (UniqueConstraint("series", "session_date"),)
    series: Mapped[str] = mapped_column(String(100), nullable=False)
    session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class DataProposal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "data_proposals"
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("market_instruments.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
