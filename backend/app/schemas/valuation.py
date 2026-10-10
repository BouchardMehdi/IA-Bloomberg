from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.schemas.international import CURRENCIES


class ReferencePE(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    value: Decimal = Field(gt=0, lt=1000000, decimal_places=6)
    label: str = Field(min_length=3, max_length=200)
    rationale: str = Field(min_length=20, max_length=1500)
    basis: Literal["annual_gaap_diluted"]
    as_of: date
    source_url: HttpUrl
    published_at: datetime


class ValuationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    valuation_date: date
    currency: str
    quote_multiplier: Decimal = Field(gt=0, le=1000, decimal_places=6)
    period_start: date
    period_end: date
    period_type: Literal["annual"]
    basis: Literal["gaap_diluted"]
    eps_per_security: Decimal = Field(gt=-1000000, lt=1000000, decimal_places=10)
    source_url: HttpUrl
    published_at: datetime
    security_basis_confirmed: Literal[True]
    security_basis_note: str = Field(min_length=20, max_length=1500)
    security_source_url: HttpUrl
    security_published_at: datetime
    reference: ReferencePE | None = None

    @field_validator("currency")
    @classmethod
    def currency_supported(cls, value):
        if value not in CURRENCIES:
            raise ValueError("Devise non prise en charge.")
        return value

    @model_validator(mode="after")
    def compatible(self):
        if not 350 <= (self.period_end - self.period_start).days + 1 <= 378:
            raise ValueError("Une période annuelle explicite de 350 à 378 jours est requise.")
        if (
            not self.period_start
            <= self.period_end
            < self.valuation_date
            <= datetime.now(UTC).date()
        ):
            raise ValueError("Période terminée avant la séance, sans date future.")
        sources = [
            (self.source_url, self.published_at),
            (self.security_source_url, self.security_published_at),
        ]
        if self.reference:
            if not 0 <= (self.valuation_date - self.reference.as_of).days <= 30:
                raise ValueError(
                    "Référence datée au plus tard à la séance et vieille de 30 jours maximum."
                )
            if (
                self.reference.published_at.tzinfo is None
                or self.reference.as_of > self.reference.published_at.astimezone(UTC).date()
            ):
                raise ValueError("Date de référence au plus tard à sa publication.")
            sources.append((self.reference.source_url, self.reference.published_at))
        for url, published in sources:
            if url.username or url.password or url.query or url.fragment:
                raise ValueError("URL documentaire sans identifiants ni paramètres requise.")
            if published.tzinfo is None or published.astimezone(UTC).date() >= self.valuation_date:
                raise ValueError("Sources datées avec fuseau, publiées avant le jour de la séance.")
        if self.published_at.astimezone(UTC).date() < self.period_end:
            raise ValueError("La publication du résultat doit suivre la fin de période.")
        return self


class ValuationBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: UUID
    observation: ValuationInput


class ValuationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ValuationBatchItem] = Field(min_length=1, max_length=100)
