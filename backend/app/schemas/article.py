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


class ArticlePage(BaseModel):
    items: list[ArticleRead]
    total: int
    limit: int
    offset: int
