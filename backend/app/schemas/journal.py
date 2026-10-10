from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ResearchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: HttpUrl
    published_at: datetime
    note: str = Field(min_length=1, max_length=1000)

    @field_validator("url")
    @classmethod
    def reference(cls, value):
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("Référence publique sans identifiants ni paramètres secrets requise.")
        return value

    @field_validator("published_at")
    @classmethod
    def published(cls, value):
        if value.tzinfo is None or value > datetime.now(UTC):
            raise ValueError("Date de publication passée avec fuseau requise.")
        return value


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    client_request_id: UUID
    title: str = Field(min_length=3, max_length=200)
    hypothesis: str = Field(min_length=10, max_length=6000)
    risks: str = Field(min_length=5, max_length=4000)
    invalidation: str = Field(min_length=5, max_length=4000)
    horizon: str = Field(min_length=2, max_length=200)
    review_on: date
    status: Literal["watching", "considering", "held", "closed", "invalidated"]
    observations: str = Field(default="", max_length=6000)
    evidence: list[ResearchEvidence] = Field(min_length=1, max_length=20)
    trade_id: UUID | None = None
    acknowledged: Literal[True]


class DecisionCreate(DecisionInput):
    instrument_id: UUID
    portfolio_id: UUID | None = None


class DecisionUpdate(DecisionInput):
    expected_version: int = Field(ge=1)
