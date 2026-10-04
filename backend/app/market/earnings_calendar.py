"""Documented Alpha Vantage calendar; dates are estimates, not announcements."""

import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from app.market.alpha_vantage import ENDPOINT, AlphaVantageClient
from app.market.providers import MarketDataError
from app.schemas.international import CURRENCIES


class CalendarRecord(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    report_date: date
    fiscal_period_end: date
    estimate: Decimal | None = Field(default=None, gt=-1_000_000, lt=1_000_000, decimal_places=6)
    currency: str
    time_of_day: str | None = Field(default=None, max_length=50)

    @field_validator("currency")
    @classmethod
    def currency_known(cls, value):
        if value not in CURRENCIES:
            raise ValueError("unknown currency")
        return value

    @model_validator(mode="after")
    def dates_valid(self):
        today = datetime.now(UTC).date()
        if not today - timedelta(days=7) <= self.report_date <= today + timedelta(days=400):
            raise ValueError("calendar date outside bounds")
        if self.fiscal_period_end > self.report_date:
            raise ValueError("invalid period")
        return self


def parse_calendar(content: str, symbol: str) -> list[CalendarRecord]:
    if content.lstrip().startswith("{"):
        try:
            payload = json.loads(content)
        except ValueError:
            raise MarketDataError("provider_invalid_response") from None
        if isinstance(payload, dict) and ("Note" in payload or "Information" in payload):
            raise MarketDataError("provider_quota")
        raise MarketDataError("provider_rejected")
    reader = csv.DictReader(io.StringIO(content))
    required_columns = {
        "symbol",
        "name",
        "reportDate",
        "fiscalDateEnding",
        "estimate",
        "currency",
    }
    columns = reader.fieldnames or []
    if (
        len(columns) != len(set(columns))
        or not required_columns.issubset(columns)
        or set(columns) - required_columns - {"timeOfTheDay"}
    ):
        raise MarketDataError("provider_invalid_response")
    records, keys = [], set()
    try:
        for row in reader:
            if len(records) >= 1000 or None in row or any(value is None for value in row.values()):
                raise ValueError("invalid row")
            record = CalendarRecord(
                symbol=row["symbol"],
                report_date=row["reportDate"],
                fiscal_period_end=row["fiscalDateEnding"],
                estimate=None if row["estimate"] in {"", "None", "null"} else row["estimate"],
                currency=row["currency"],
                time_of_day=row.get("timeOfTheDay") or None,
            )
            if record.symbol != symbol:
                raise MarketDataError("symbol_mismatch")
            key = (record.fiscal_period_end, record.report_date)
            if key in keys:
                raise ValueError("duplicate row")
            keys.add(key)
            records.append(record)
    except MarketDataError:
        raise
    except (ValueError, TypeError, KeyError):
        raise MarketDataError("provider_invalid_response") from None
    return records


def validate_calendar_batch(records, source_url: str, symbol: str):
    url = urlsplit(source_url)
    params = parse_qsl(url.query, keep_blank_values=True)
    if (
        url.scheme != "https"
        or url.netloc != "www.alphavantage.co"
        or url.path != "/query"
        or url.fragment
        or len(params) != 3
        or dict(params) != {"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": "3month"}
        or len(records) > 1000
    ):
        raise MarketDataError("provider_invalid_response")
    validated = [CalendarRecord.model_validate(record.model_dump()) for record in records]
    if any(record.symbol != symbol for record in validated):
        raise MarketDataError("symbol_mismatch")
    if len({(item.fiscal_period_end, item.report_date) for item in validated}) != len(validated):
        raise MarketDataError("provider_invalid_response")
    return validated


class EarningsCalendarClient(AlphaVantageClient):
    async def calendar(self, symbol: str) -> tuple[list[CalendarRecord], str]:
        params = {"function": "EARNINGS_CALENDAR", "symbol": symbol, "horizon": "3month"}
        source_url = f"{ENDPOINT}?{urlencode(params)}"
        try:
            async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
                async with client.stream(
                    "GET", ENDPOINT, params={**params, "apikey": self.api_key}
                ) as response:
                    if response.status_code == 429:
                        raise MarketDataError("provider_quota")
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 1_000_000:
                            raise MarketDataError("response_too_large")
            return parse_calendar(body.decode("utf-8-sig"), symbol), source_url
        except httpx.TimeoutException:
            raise MarketDataError("provider_timeout") from None
        except httpx.HTTPError:
            raise MarketDataError("provider_http_error") from None
        except UnicodeError:
            raise MarketDataError("provider_invalid_response") from None
