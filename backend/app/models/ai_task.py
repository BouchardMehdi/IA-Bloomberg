import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDPrimaryKeyMixin


class AiTask(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_tasks"

    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    model_name: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(80))
    source_name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    input_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_id: Mapped[uuid.UUID | None]
    result: Mapped[dict | None] = mapped_column(JSONB)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class AiWorkerState(Base):
    __tablename__ = "ai_worker_state"
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model_name: Mapped[str] = mapped_column(String(200))
