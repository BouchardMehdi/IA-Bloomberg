import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    cik: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)

    event_links = relationship("EventCompany", back_populates="company")


class EventCompany(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "event_companies"
    __table_args__ = (UniqueConstraint("event_id", "company_id"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), default="subject", nullable=False)

    event = relationship("Event", back_populates="company_links")
    company = relationship("Company", back_populates="event_links")
