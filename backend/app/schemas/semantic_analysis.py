from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    claim: str = Field(min_length=3, max_length=500)
    quote: str = Field(min_length=3, max_length=500)


class ExtractedAmount(BaseModel):
    value: float
    currency: str | None = Field(default=None, max_length=10)
    unit: str | None = Field(default=None, max_length=30)
    context: str = Field(min_length=3, max_length=300)


class SemanticExtraction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    summary: str = Field(min_length=10, max_length=1500)
    event_type: Literal[
        "monetary_policy",
        "financial_results",
        "corporate_action",
        "regulation",
        "enforcement",
        "regulatory_filing",
        "other",
    ]
    companies: list[str] = Field(default_factory=list, max_length=20)
    assets: list[str] = Field(default_factory=list, max_length=20)
    dates: list[str] = Field(default_factory=list, max_length=20)
    amounts: list[ExtractedAmount] = Field(default_factory=list, max_length=20)
    sentiment_score: float = Field(ge=-1, le=1)
    importance_score: float = Field(ge=0, le=1)
    urgency_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    evidence: list[EvidenceItem] = Field(min_length=1, max_length=10)
