"""Explicit supplied observations; no guessing of tickers, FX direction or units."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

CURRENCIES = {
    "USD",
    "EUR",
    "GBP",
    "HKD",
    "JPY",
    "CHF",
    "CAD",
    "AUD",
    "CNY",
    "SGD",
    "NZD",
    "SEK",
    "NOK",
    "DKK",
    "INR",
    "KRW",
    "TWD",
    "BRL",
    "ZAR",
    "MXN",
}


class SourcedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_url: HttpUrl
    as_of: date

    @field_validator("as_of")
    @classmethod
    def not_future(cls, value):
        if value > datetime.now(UTC).date():
            raise ValueError("Une observation ne peut pas être datée dans le futur.")
        return value

    @field_validator("source_url")
    @classmethod
    def public_reference(cls, value):
        if value.username or value.password or value.query or value.fragment:
            raise ValueError(
                "Utiliser une URL de référence sans identifiants ni paramètres secrets."
            )
        return value


class InternationalInstrumentCreate(SourcedObservation):
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,19}$")
    exchange: str = Field(pattern=r"^[A-Z0-9]{4}$", description="Explicit listing MIC")
    name: str = Field(min_length=1, max_length=512)
    isin: str = Field(pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
    bloomberg_symbol: str | None = Field(default=None, min_length=1, max_length=100)
    cik: str | None = Field(default=None, pattern=r"^[0-9]{10}$")
    currency: str
    quote_multiplier: Decimal = Field(gt=0, le=1, decimal_places=6)
    asset_class: Literal["equity"]

    @field_validator("currency")
    @classmethod
    def currency_supported(cls, value):
        if value not in CURRENCIES:
            raise ValueError("Devise non prise en charge dans cette version.")
        return value

    @field_validator("exchange")
    @classmethod
    def non_us_listing(cls, value):
        if value in {"XNYS", "XNAS"}:
            raise ValueError("Utiliser l'ajout SEC NYSE/Nasdaq pour ces marchés.")
        return value

    @field_validator("isin")
    @classmethod
    def valid_isin_checksum(cls, value):
        digits = "".join(str(int(c, 36)) if c.isalpha() else c for c in value)
        total = 0
        for index, digit in enumerate(reversed(digits)):
            number = int(digit) * (2 if index % 2 else 1)
            total += number // 10 + number % 10
        if total % 10:
            raise ValueError("Clé de contrôle ISIN invalide.")
        return value


class LocalPriceCreate(SourcedObservation):
    currency: str
    quote_multiplier: Decimal = Field(gt=0, le=1, decimal_places=6)
    close: Decimal = Field(gt=0, lt=100_000_000_000_000, decimal_places=6)
    volume: int = Field(ge=0, le=9_000_000_000_000_000_000, strict=True)


class FxRateCreate(SourcedObservation):
    currency: str
    usd_per_unit: Decimal = Field(gt=0, lt=10_000_000_000, decimal_places=10)

    @field_validator("currency")
    @classmethod
    def non_usd_currency(cls, value):
        if value not in CURRENCIES - {"USD"}:
            raise ValueError("Fournir une devise prise en charge autre que USD.")
        return value
