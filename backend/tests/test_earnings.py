from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.market.earnings_calendar import (
    EarningsCalendarClient,
    parse_calendar,
    validate_calendar_batch,
)
from app.market.providers import MarketDataError
from app.schemas.earnings import EarningsInput
from app.services.earnings import compare_eps

HEADER = "symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
REPORT = datetime.now(UTC).date() + timedelta(days=20)
PERIOD = REPORT - timedelta(days=40)
SOURCE = "https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&symbol=IBM&horizon=3month"


def csv_body(estimate="0", symbol="IBM", currency="USD"):
    return HEADER + f"{symbol},IBM,{REPORT},{PERIOD},{estimate},{currency}\n"


@pytest.mark.parametrize("value", ["0", "-1.23", "2.456789", "", "None"])
def test_calendar_numbers_and_empty_estimates(value):
    row = parse_calendar(csv_body(value), "IBM")[0]
    assert row.estimate == (Decimal(value) if value not in {"", "None"} else None)


@pytest.mark.parametrize(
    "body",
    [
        "{}",
        '{"Note":"secret"}',
        "bad headers",
        csv_body("NaN"),
        csv_body("Infinity"),
        csv_body("1.1234567"),
        csv_body(currency="BAD"),
        csv_body(symbol="OTHER"),
        csv_body() + csv_body().splitlines()[1] + "\n",
    ],
)
def test_reject_entire_bad_response(body):
    with pytest.raises(MarketDataError):
        parse_calendar(body, "IBM")


def test_header_only_calendar_is_not_fake_data():
    assert parse_calendar(HEADER, "IBM") == []


def test_revalidate_provenance_and_mutated_last_record():
    records = parse_calendar(csv_body(), "IBM")
    for url in [
        SOURCE + "&apikey=secret",
        SOURCE.replace("www.alphavantage.co", "evil.example"),
        SOURCE + "#secret",
    ]:
        with pytest.raises(MarketDataError):
            validate_calendar_batch(records, url, "IBM")
    with pytest.raises(ValidationError):
        validate_calendar_batch(
            [records[0].model_copy(update={"estimate": Decimal("NaN")})], SOURCE, "IBM"
        )


@pytest.mark.asyncio
async def test_http_bounded_quota_and_public_source():
    client = EarningsCalendarClient(
        "test-secret",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=csv_body())),
    )
    records, source = await client.calendar("IBM")
    assert len(records) == 1 and "test-secret" not in source
    validate_calendar_batch(records, source, "IBM")
    for response, expected in [
        (httpx.Response(429), "provider_quota"),
        (httpx.Response(200, content=b"x" * 1_000_001), "response_too_large"),
    ]:
        client.transport = httpx.MockTransport(lambda request, response=response: response)
        with pytest.raises(MarketDataError) as error:
            await client.calendar("IBM")
        assert error.value.code == expected


def manual(**changes):
    return {
        "kind": "estimate",
        "report_date": str(REPORT),
        "fiscal_period_end": str(PERIOD),
        "published_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "source_url": "https://example.org/results",
        "eps": "0",
        "currency": "USD",
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"published_at": "2020-01-01T00:00:00"},
        {"source_url": "https://example.org/?apikey=secret"},
        {"kind": "schedule"},
        {"kind": "reported"},
        {"currency": None},
        {"eps": "NaN"},
        {"fiscal_period_end": str(REPORT + timedelta(days=1))},
    ],
)
def test_invalid_manual_source_or_result(changes):
    with pytest.raises(ValidationError):
        EarningsInput(**manual(**changes))


def pair():
    result = {
        "id": "result",
        "kind": "reported",
        "basis": "gaap_diluted",
        "period_type": "quarterly",
        "currency": "USD",
        "eps": "1",
        "fiscal_period_end": "2026-06-30",
        "published_at": "2026-08-01T12:00:00Z",
    }
    estimate = {
        **result,
        "id": "estimate",
        "kind": "estimate",
        "eps": "0",
        "source_url": "https://example.org/estimate",
        "published_at": "2026-07-31T00:00:00Z",
        "observed_at": "2026-07-31T01:00:00+00:00",
    }
    return result, estimate


def test_zero_and_negative_forecasts_are_real_values():
    result, estimate = pair()
    comparison = compare_eps(result, [estimate])
    assert comparison["delta"] == 1 and comparison["percent"] is None
    comparison = compare_eps(result, [{**estimate, "eps": "-1"}])
    assert comparison["delta"] == 2 and comparison["percent"] == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "EUR"},
        {"period_type": "annual"},
        {"basis": "unknown"},
        {"published_at": None},
        {"fiscal_period_end": "2026-03-31"},
        {"observed_at": "2026-08-01T12:00:00Z"},
    ],
)
def test_no_hindsight_or_incompatible_comparison(changes):
    result, estimate = pair()
    assert compare_eps(result, [{**estimate, **changes}])["status"] == "not_comparable"


def test_ambiguous_and_adjusted_earnings_excluded():
    result, estimate = pair()
    assert (
        compare_eps(result, [estimate, {**estimate, "id": "other"}])["status"] == "not_comparable"
    )
    result["basis"] = "adjusted_diluted"
    assert compare_eps(result, [estimate])["status"] == "not_comparable"
