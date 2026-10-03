import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventCompanyRead(BaseModel):
    id: uuid.UUID
    cik: str
    name: str
    role: str


class SemanticAnalysisRead(BaseModel):
    model_name: str
    prompt_version: str
    duration_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    result: dict[str, Any]
    source_url: str | None = None


class EventSourceRead(BaseModel):
    article_id: uuid.UUID
    source_name: str
    url: str
    document_url: str | None
    published_at: datetime | None
    content_status: str
    is_primary_source: bool


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
    semantic_analysis: SemanticAnalysisRead | None = None
    sources: list[EventSourceRead] = Field(default_factory=list)


class EventPage(BaseModel):
    items: list[EventRead]
    total: int
    limit: int
    offset: int
