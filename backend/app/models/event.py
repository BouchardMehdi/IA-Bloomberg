import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Event(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"

    deduplication_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    merged_into_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"))
    parent_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id"), index=True)
    fact_analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", name="fk_events_fact_run", use_alter=True)
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_time_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="detected", nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    extraction_version: Mapped[str | None] = mapped_column(String(50))
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    importance_score: Mapped[float | None] = mapped_column(Float)
    impact_score: Mapped[float | None] = mapped_column(Float)
    novelty_score: Mapped[float | None] = mapped_column(Float)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    urgency_score: Mapped[float | None] = mapped_column(Float)
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    country: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(50))

    article_links = relationship("EventArticle", back_populates="event")
    company_links = relationship("EventCompany", back_populates="event")
    analysis_runs = relationship(
        "AnalysisRun",
        back_populates="event",
        order_by="AnalysisRun.started_at.desc()",
        foreign_keys="AnalysisRun.event_id",
    )
    fact_analysis_run = relationship("AnalysisRun", foreign_keys=[fact_analysis_run_id])


class EventArticle(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "event_articles"
    __table_args__ = (UniqueConstraint("event_id", "article_id"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    is_primary_source: Mapped[bool] = mapped_column(default=False, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)

    event = relationship("Event", back_populates="article_links")
    article = relationship("Article", back_populates="event_links")
