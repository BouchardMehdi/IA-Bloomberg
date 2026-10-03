import uuid
from datetime import datetime

from pydantic import BaseModel


class ArticleRead(BaseModel):
    id: uuid.UUID
    source_name: str
    url: str
    title: str
    content: str | None
    language: str | None
    published_at: datetime | None
    fetched_at: datetime
    document_url: str | None = None
    content_status: str = "pending"
    content_attempts: int = 0
    content_fetched_at: datetime | None = None
    content_truncated: bool = False
    content_error: str | None = None


class ArticleDetail(ArticleRead):
    full_content: str | None = None


class ArticlePage(BaseModel):
    items: list[ArticleRead]
    total: int
    limit: int
    offset: int
