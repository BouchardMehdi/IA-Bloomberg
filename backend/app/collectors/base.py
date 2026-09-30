from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NormalizedArticle(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str | None = None
    url: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=1024)
    content: str | None = None
    language: str | None = Field(default=None, max_length=10)
    author: str | None = Field(default=None, max_length=255)
    published_at: datetime | None = None
    fetched_at: datetime
    content_hash: str = Field(min_length=64, max_length=64)


class BaseCollector(ABC):
    source_name: str
    source_url: str
    source_type: str
    country: str | None = None
    region: str | None = None
    reliability_score: float = 0.5

    @abstractmethod
    async def fetch(self) -> bytes:
        """Fetch raw source data without persisting it."""

    @abstractmethod
    def normalize(self, payload: bytes) -> list[NormalizedArticle]:
        """Convert raw source data into the shared article contract."""

    async def collect(self) -> list[NormalizedArticle]:
        return self.normalize(await self.fetch())
