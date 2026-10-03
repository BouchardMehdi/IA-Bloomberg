import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Article(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "articles"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    full_content: Mapped[str | None] = mapped_column(Text)
    full_content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    document_url: Mapped[str | None] = mapped_column(String(2048))
    content_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    content_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_error: Mapped[str | None] = mapped_column(Text)
    content_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10))
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))

    source = relationship("Source", back_populates="articles")
    event_links = relationship("EventArticle", back_populates="article")
