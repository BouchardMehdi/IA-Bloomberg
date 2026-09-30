import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CollectionRunRead(BaseModel):
    id: uuid.UUID
    source_name: str
    trigger: Literal["manual", "scheduled"]
    status: Literal["running", "success", "failed"]
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    error_message: str | None


class CollectionRunPage(BaseModel):
    items: list[CollectionRunRead]
    total: int
    limit: int
    offset: int
