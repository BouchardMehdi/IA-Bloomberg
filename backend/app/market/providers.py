"""Provider contract for raw daily closes, independent of HTTP and persistence."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol
from urllib.parse import parse_qsl
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.schemas.international import CURRENCIES

ERROR_CODES = {
    "provider_http_error",
    "provider_invalid_response",
    "provider_rejected_or_quota",
    "provider_rejected",
    "provider_quota",
    "provider_timeout",
    "provider_internal_error",
    "response_too_large",
    "symbol_mismatch",
    "invalid_price",
    "invalid_price_payload",
    "unsupported_listing",
    "quote_identity_mismatch",
    "invalid_quote_batch",
}


class MarketDataError(ValueError):
    def __init__(self, code: str):
        # Never persist arbitrary exceptions or provider bodies, which can contain keys.
        self.code = code if code in ERROR_CODES else "provider_internal_error"
        super().__init__(self.code)


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuoteIdentity(ImmutableModel):
    instrument_id: UUID
    symbol: str = Field(min_length=1, max_length=32)
    exchange: str = Field(min_length=1, max_length=50)
    currency: str
    quote_multiplier: Decimal = Field(gt=0, le=1, decimal_places=6)

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value):
        if value not in CURRENCIES:
            raise ValueError("unsupported currency")
        return value

    @classmethod
    def from_instrument(cls, instrument):
        return cls(
            **{
                name: getattr(instrument, "id" if name == "instrument_id" else name)
                for name in cls.model_fields
            }
        )


class DailyClose(ImmutableModel):
    session_date: date
    close: Decimal = Field(gt=0, lt=100_000_000_000_000, decimal_places=6)
    volume: int = Field(strict=True, ge=0, le=9_000_000_000_000_000_000)

    @field_validator("session_date")
    @classmethod
    def not_future(cls, value):
        if value > datetime.now(UTC).date():
            raise ValueError("future close")
        return value


class QuoteBatch(ImmutableModel):
    identity: QuoteIdentity
    provider: str = Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")
    provider_symbol: str = Field(min_length=1, max_length=100)
    source_url: HttpUrl
    adjusted: Literal[False] = False
    records: tuple[DailyClose, ...] = Field(min_length=1, max_length=1000)
    mapping_evidence: dict | None = None

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value):
        # Only Alpha Vantage's public request parameters are currently supported.
        # Future adapters must provide a public documentary URL, without credentials.
        if value.username or value.password or value.fragment:
            raise ValueError("unsafe provenance")
        query = parse_qsl(value.query or "", keep_blank_values=True)
        expected = {"function": "TIME_SERIES_DAILY", "symbol": None, "outputsize": "compact"}
        if query and (
            value.host != "www.alphavantage.co"
            or value.path != "/query"
            or len(query) != 3
            or set(dict(query)) != set(expected)
            or any(expected[k] is not None and v != expected[k] for k, v in query)
        ):
            raise ValueError("unsafe provenance parameters")
        return value

    @model_validator(mode="after")
    def unique_dates(self):
        if len({r.session_date for r in self.records}) != len(self.records):
            raise ValueError("duplicate session date")
        return self

    def context(self) -> dict:
        context = {
            **self.identity.model_dump(mode="json"),
            "provider_symbol": self.provider_symbol,
            "adjusted": self.adjusted,
        }
        if self.mapping_evidence is not None:
            context["mapping_evidence"] = self.mapping_evidence
        return context


class ProviderPolicy(ImmutableModel):
    provider: str = Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")
    daily_request_budget: int = Field(ge=1, le=100_000)
    retry_seconds: int = Field(default=300, ge=60, le=86400)
    timeout_seconds: int = Field(default=90, ge=1, le=120)

    def retry_at(self, code: str, now: datetime) -> datetime:
        if code in {"provider_quota", "provider_rejected_or_quota"}:
            return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return now + timedelta(seconds=self.retry_seconds)


class PriceProvider(Protocol):
    policy: ProviderPolicy

    def supports(self, identity: QuoteIdentity) -> bool: ...

    async def fetch(self, identity: QuoteIdentity) -> QuoteBatch: ...


def validate_batch(batch: QuoteBatch, identity: QuoteIdentity, provider: str) -> QuoteBatch:
    # Revalidate even model_construct / mutable third-party adapter results before any write.
    try:
        batch = QuoteBatch.model_validate(batch.model_dump(mode="python"))
    except (ValueError, TypeError, AttributeError):
        raise MarketDataError("invalid_quote_batch") from None
    if batch.identity != identity or batch.provider != provider:
        raise MarketDataError("quote_identity_mismatch")
    return batch
