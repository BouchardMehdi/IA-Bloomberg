from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(50))
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    articles = relationship("Article", back_populates="source")
    collection_runs = relationship("CollectionRun", back_populates="source")
