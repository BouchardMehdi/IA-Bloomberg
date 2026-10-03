"""Official daily endpoint, raw closes; sanitized provenance and errors."""

import logging
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx

ENDPOINT = "https://www.alphavantage.co/query"


class RedactAPIKey(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"(apikey=)[^&\s\"']+", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


logging.getLogger("httpx").addFilter(RedactAPIKey())


class MarketDataError(ValueError):
    pass


def parse_daily(payload: dict, symbol: str, today: date | None = None) -> list[dict]:
    today = today or datetime.now(UTC).date()
    series = payload.get("Time Series (Daily)")
    metadata = payload.get("Meta Data", {})
    if not isinstance(series, dict) or not series:
        raise MarketDataError("provider_rejected_or_quota")
    if not isinstance(metadata, dict) or metadata.get("2. Symbol") != symbol:
        raise MarketDataError("symbol_mismatch")
    records = []
    try:
        for day, item in series.items():
            session_date = date.fromisoformat(day)
            close = Decimal(item["4. close"])
            volume = int(item["5. volume"])
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
    def __init__(self, api_key: str, *, transport=None):
        self.api_key = api_key
        self.transport = transport

    async def daily(self, symbol: str) -> tuple[list[dict], str]:
        params = {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"}
        source_url = f"{ENDPOINT}?{urlencode(params)}"
        try:
            async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
                async with client.stream(
                    "GET", ENDPOINT, params={**params, "apikey": self.api_key}
                ) as r:
                    r.raise_for_status()
                    raw = bytearray()
                    async for chunk in r.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1_000_000:
                            raise MarketDataError("response_too_large")
                    import json

                    payload = json.loads(raw)
        except httpx.HTTPError:
            raise MarketDataError("provider_http_error") from None
        except (ValueError, TypeError):
            raise MarketDataError("provider_invalid_response") from None
        if not isinstance(payload, dict):
            raise MarketDataError("provider_invalid_response")
        return parse_daily(payload, symbol), source_url
