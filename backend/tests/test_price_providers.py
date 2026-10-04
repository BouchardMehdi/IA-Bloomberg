from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.market.alpha_vantage import AlphaVantageClient, parse_daily
from app.market.provider_registry import configured_price_providers, price_provider_catalog
from app.market.providers import (
    MarketDataError,
    ProviderPolicy,
    QuoteBatch,
    QuoteIdentity,
    validate_batch,
)


def identity(**overrides):
    return QuoteIdentity(
        instrument_id=uuid4(),
        symbol="02600",
        exchange="XHKG",
        currency="HKD",
        quote_multiplier=Decimal("1"),
    ).model_copy(update=overrides)


def batch(request, **overrides):
    values = {
        "identity": request,
        "provider": "fixture",
        "provider_symbol": "02600.fixture",
        "source_url": "https://example.org/quotes/02600",
        "records": [
            {"session_date": datetime.now(UTC).date(), "close": "10.123456", "volume": 100}
        ],
    }
    return QuoteBatch(**{**values, **overrides})


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "USD"),
        ("exchange", "XLON"),
        ("symbol", "2600"),
        ("quote_multiplier", Decimal("0.01")),
        ("instrument_id", uuid4()),
    ],
)
def test_batch_must_match_exact_listing_and_conventions(field, value):
    request = identity()
    response = batch(request.model_copy(update={field: value}))
    with pytest.raises(MarketDataError, match="quote_identity_mismatch"):
        validate_batch(response, request, "fixture")


def test_provider_identity_is_checked_and_numeric_symbols_are_preserved():
    request = identity()
    response = validate_batch(batch(request), request, "fixture")
    assert response.context()["symbol"] == "02600"
    assert response.context()["exchange"] == "XHKG"
    assert response.context()["currency"] == "HKD"
    with pytest.raises(MarketDataError, match="quote_identity_mismatch"):
        validate_batch(response, request, "other")


@pytest.mark.parametrize(
    "close,volume",
    [
        ("NaN", 1),
        ("Infinity", 1),
        ("0", 1),
        ("-1", 1),
        ("0.1234567", 1),
        ("10", None),
        ("10", 1.5),
        ("10", True),
        ("10", -1),
    ],
)
def test_invalid_or_missing_values_are_rejected(close, volume):
    with pytest.raises(ValidationError):
        batch(
            identity(),
            records=[{"session_date": datetime.now(UTC).date(), "close": close, "volume": volume}],
        )


def test_empty_duplicate_future_and_adjusted_series_are_rejected():
    row = {"session_date": datetime.now(UTC).date(), "close": "10", "volume": 100}
    for overrides in (
        {"records": []},
        {"records": [row, row]},
        {"records": [{**row, "session_date": row["session_date"] + timedelta(days=1)}]},
        {"adjusted": True},
    ):
        with pytest.raises(ValidationError):
            batch(identity(), **overrides)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/quote?apikey=secret",
        "https://user:password@example.org/quote",
        "https://example.org/quote#secret",
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=EX&outputsize=compact&apikey=secret",
    ],
)
def test_credentials_are_not_accepted_in_provenance(url):
    with pytest.raises(ValidationError):
        batch(identity(), source_url=url)


def test_constructed_models_are_revalidated_and_error_text_is_sanitized():
    request = identity()
    invalid = batch(request).model_copy(update={"records": ()})
    with pytest.raises(MarketDataError, match="invalid_quote_batch"):
        validate_batch(invalid, request, "fixture")
    assert str(MarketDataError("secret-key and provider body")) == "provider_internal_error"


@pytest.mark.asyncio
async def test_alpha_adapter_has_explicit_limited_coverage_and_safe_source():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "Meta Data": {"2. Symbol": "EX"},
                "Time Series (Daily)": {
                    datetime.now(UTC).date().isoformat(): {"4. close": "10", "5. volume": "100"}
                },
            },
        )

    provider = AlphaVantageClient("fixture-secret", transport=httpx.MockTransport(handler))
    request = identity(symbol="EX", exchange="NYSE", currency="USD")
    result = validate_batch(await provider.fetch(request), request, "alpha_vantage")
    assert result.provider_symbol == "EX" and "fixture-secret" not in str(result.source_url)
    for unsupported in (
        identity(),
        request.model_copy(update={"currency": "EUR"}),
        request.model_copy(update={"quote_multiplier": Decimal("0.01")}),
    ):
        with pytest.raises(MarketDataError, match="unsupported_listing"):
            await provider.fetch(unsupported)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", [httpx.Response(429), httpx.Response(200, json={"Note": "secret quota text"})]
)
async def test_provider_quota_is_classified_without_body(response):
    provider = AlphaVantageClient(
        "fixture-secret", transport=httpx.MockTransport(lambda _: response)
    )
    with pytest.raises(MarketDataError, match="^provider_quota$"):
        await provider.daily("EX")


def test_retry_policy_and_explicit_configuration():
    now = datetime(2026, 10, 3, 14, 30, tzinfo=UTC)
    policy = ProviderPolicy(provider="fixture", daily_request_budget=1)
    assert policy.retry_at("provider_http_error", now) == now + timedelta(minutes=5)
    assert policy.retry_at("provider_quota", now) == datetime(2026, 10, 4, tzinfo=UTC)
    settings = Settings(alpha_vantage_api_key="")
    assert configured_price_providers(settings) == ()
    assert not price_provider_catalog(settings)[0]["configured"]
    configured = configured_price_providers(
        Settings(alpha_vantage_api_key="fixture", market_daily_request_budget=3)
    )
    assert configured[0].policy.daily_request_budget == 3


@pytest.mark.parametrize("volume", [1.5, 1.0, True, None, "1.5", "-1"])
def test_alpha_parser_never_rounds_or_invents_volume(volume):
    payload = {
        "Meta Data": {"2. Symbol": "EX"},
        "Time Series (Daily)": {
            datetime.now(UTC).date().isoformat(): {"4. close": "10", "5. volume": volume}
        },
    }
    with pytest.raises(MarketDataError):
        parse_daily(payload, "EX")
