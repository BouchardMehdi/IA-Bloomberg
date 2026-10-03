from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InstrumentCreate(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,19}$")
    exchange: Literal["NYSE", "Nasdaq"] | None = None


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    initial_capital: Decimal = Field(
        default=Decimal("1000000"), ge=1, le=1_000_000_000, decimal_places=2
    )
    currency: Literal["USD"] = "USD"
    fee_bps: Decimal = Field(default=Decimal("10"), ge=0, le=1000, decimal_places=2)
    max_position_pct: Decimal = Field(default=Decimal("25"), gt=0, le=100, decimal_places=2)
    allowed_symbols: list[str] = Field(default_factory=list, max_length=100)
    starts_on: date | None = None
    ends_on: date | None = None

    @field_validator("allowed_symbols")
    @classmethod
    def valid_symbols(cls, symbols):
        return sorted({InstrumentCreate(symbol=s.strip().upper()).symbol for s in symbols})

    @model_validator(mode="after")
    def valid_dates(self):
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("End date must follow start date")
        return self


class PaperOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: UUID
    client_order_id: UUID
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=1_000_000, strict=True)
