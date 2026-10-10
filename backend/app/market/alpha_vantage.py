"""Official daily endpoint, raw closes; sanitized provenance and errors."""

import logging
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx

from app.market.providers import MarketDataError, ProviderPolicy, QuoteBatch, QuoteIdentity

ENDPOINT = "https://www.alphavantage.co/query"


class RedactAPIKey(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"(apikey=)[^&\s\"']+", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


logging.getLogger("httpx").addFilter(RedactAPIKey())


def parse_daily(payload: dict, symbol: str, today: date | None = None) -> list[dict]:
    today = today or datetime.now(UTC).date()
    series = payload.get("Time Series (Daily)")
    metadata = payload.get("Meta Data", {})
    if not isinstance(series, dict) or not series:
        if "Note" in payload or "Information" in payload:
            raise MarketDataError("provider_quota")
        raise MarketDataError("provider_rejected_or_quota")
    if not isinstance(metadata, dict) or metadata.get("2. Symbol") != symbol:
        raise MarketDataError("symbol_mismatch")
    records = []
    try:
        for day, item in series.items():
            session_date = date.fromisoformat(day)
            close = Decimal(item["4. close"])
            raw_volume = item["5. volume"]
            if (
                isinstance(raw_volume, bool)
                or not isinstance(raw_volume, str | int)
                or not re.fullmatch(r"[0-9]+", str(raw_volume))
            ):
                raise MarketDataError("invalid_price_payload")
            volume = int(raw_volume)
            if (
                session_date > today
                or not close.is_finite()
                or close <= 0
                or close >= Decimal("100000000000000")
                or volume < 0
                or volume > 9_000_000_000_000_000_000
                or close.as_tuple().exponent < -6
            ):
                raise MarketDataError("invalid_price")
            records.append({"session_date": session_date, "close": close, "volume": volume})
    except (KeyError, TypeError, InvalidOperation, ValueError):
        raise MarketDataError("invalid_price_payload") from None
    return sorted(records, key=lambda r: r["session_date"])


class AlphaVantageClient:
    def __init__(self, api_key: str, *, transport=None, daily_request_budget: int = 20):
        self.api_key = api_key
        self.transport = transport
        self.mappings = {}
        self.policy = ProviderPolicy(
            provider="alpha_vantage", daily_request_budget=min(daily_request_budget, 25)
        )

    def supports(self, identity: QuoteIdentity) -> bool:
        if identity.exchange not in {"NYSE", "Nasdaq"}:
            mapping = self.mappings.get(str(identity.instrument_id))
            if not mapping:
                return False
            try:
                mapped = QuoteIdentity.model_validate(
                    {k: mapping.get(k) for k in QuoteIdentity.model_fields}
                )
                return mapped == identity
            except ValueError:
                return False
        return (
            identity.exchange in {"NYSE", "Nasdaq"}
            and identity.currency == "USD"
            and identity.quote_multiplier == 1
        )

    async def fetch(self, identity: QuoteIdentity) -> QuoteBatch:
        if not self.supports(identity):
            raise MarketDataError("unsupported_listing")
        mapping = self.mappings.get(str(identity.instrument_id))
        symbol = mapping["provider_symbol"] if mapping else identity.symbol
        records, source_url = await self.daily(symbol)
        return QuoteBatch(
            identity=identity,
            provider=self.policy.provider,
            provider_symbol=symbol,
            mapping_evidence=mapping,
            source_url=source_url,
            records=records,
        )

    async def daily(self, symbol: str) -> tuple[list[dict], str]:
        params = {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"}
        source_url = f"{ENDPOINT}?{urlencode(params)}"
        try:
            async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
                async with client.stream(
                    "GET", ENDPOINT, params={**params, "apikey": self.api_key}
                ) as r:
                    if r.status_code == 429:
                        raise MarketDataError("provider_quota")
                    r.raise_for_status()
                    raw = bytearray()
                    async for chunk in r.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1_000_000:
                            raise MarketDataError("response_too_large")
                    import json

                    payload = json.loads(raw)
        except MarketDataError:
            raise
        except httpx.HTTPError:
            raise MarketDataError("provider_http_error") from None
        except (ValueError, TypeError):
            raise MarketDataError("provider_invalid_response") from None
        if not isinstance(payload, dict):
            raise MarketDataError("provider_invalid_response")
        return parse_daily(payload, symbol), source_url
