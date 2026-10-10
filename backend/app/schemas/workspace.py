from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.earnings import EarningsInput
from app.schemas.international import LocalPriceCreate, FxRateCreate
from app.schemas.portfolio_tracking import CorporateActionInput, SourceDeclaration
from app.schemas.valuation import ValuationInput


class ProfileInput(SourceDeclaration):
    sector: str | None = Field(default=None, min_length=2, max_length=100)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    as_of: date

    @model_validator(mode="after")
    def dated(self):
        if not self.published_at.date() <= self.as_of <= datetime.now(UTC).date():
            raise ValueError("Classification datée après sa source et non future requise.")
        if self.sector is None and self.country is None:
            raise ValueError("Au moins un secteur ou pays documenté requis.")
        return self


class BenchmarkInput(SourceDeclaration):
    series: str = Field(pattern=r"^[A-Za-z0-9_.:-]{2,100}$")
    name: str = Field(min_length=2, max_length=150)
    session_date: date
    level: Decimal = Field(gt=0, lt=1_000_000_000_000, decimal_places=8)
    currency: Literal["USD"]
    convention: Literal["price", "net_total_return", "gross_total_return"]

    @model_validator(mode="after")
    def dated(self):
        if self.session_date > self.published_at.astimezone(UTC).date():
            raise ValueError("Une valeur d’indice ne peut pas précéder sa séance.")
        return self


class BenchmarkBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BenchmarkInput] = Field(min_length=1, max_length=1000)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: UUID


class EarningsRecord(Record):
    kind: Literal["earnings"]
    observation: EarningsInput


class ValuationRecord(Record):
    kind: Literal["valuation"]
    observation: ValuationInput


class ActionRecord(Record):
    kind: Literal["corporate_action"]
    observation: CorporateActionInput


class PriceRecord(Record):
    kind: Literal["price"]
    observation: LocalPriceCreate


class FxRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["fx"]
    observation: FxRateCreate


class DataBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Annotated[EarningsRecord | ValuationRecord | ActionRecord | PriceRecord | FxRecord,
                          Field(discriminator="kind")]] = Field(min_length=1, max_length=100)
