from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class WlsIdentityObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "wls_identity_observations"
    __table_args__ = (Index("ix_wls_identity_lookup", "source_hash", "bloomberg_identifier"),)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    bloomberg_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    query_key: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    query: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB)
