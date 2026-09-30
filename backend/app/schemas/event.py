import uuid
from datetime import datetime

from pydantic import BaseModel


class EventRead(BaseModel):
    id: uuid.UUID
    event_type: str
    title: str
    description: str | None
    event_datetime: datetime | None
    status: str
    confidence_score: float | None
    country: str | None
    region: str | None
    source_name: str
    article_url: str


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int
