import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventCompanyRead(BaseModel):
    id: uuid.UUID
    cik: str
    name: str
    role: str


class EventRead(BaseModel):
    id: uuid.UUID
    event_type: str
    title: str
    description: str | None
    event_datetime: datetime | None
    status: str
    extraction_method: str | None
    extraction_version: str | None
    evidence_excerpt: str | None
    structured_data: dict[str, Any] | None
    confidence_score: float | None
    country: str | None
    region: str | None
    source_name: str
    article_url: str
    companies: list[EventCompanyRead]


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int
