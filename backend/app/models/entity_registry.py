from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntityRegistry(Base):
    __tablename__ = "entity_registries"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    records: Mapped[list] = mapped_column(JSONB, nullable=False)
