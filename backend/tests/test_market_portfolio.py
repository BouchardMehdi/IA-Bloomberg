import logging
from datetime import date
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.market.alpha_vantage import AlphaVantageClient, MarketDataError, parse_daily
from app.market.paper import calculate_fill, check_concentration
from app.schemas.market import PaperOrder, PortfolioCreate


def payload(close="100.1200", symbol="EX", day="2026-10-01"):
    return {
        "Meta Data": {"2. Symbol": symbol},
        "Time Series (Daily)": {
            day: {"4. close": close, "5. volume": "1000"},
        },
    }


def test_daily_prices_use_decimal_and_session_dates():
    record = parse_daily(payload(), "EX", date(2026, 10, 3))[0]
    assert record["close"] == Decimal("100.12")
    assert record["session_date"] == date(2026, 10, 1)
    assert record["volume"] == 1000


@pytest.mark.parametrize("close", ["NaN", "Infinity", "-10", "0", "text", "0.1234567"])
def test_provider_invalid_prices_are_rejected(close):
    with pytest.raises(MarketDataError):
        parse_daily(payload(close), "EX", date(2026, 10, 3))


def test_future_and_mismatched_prices_and_quotas_are_not_accepted():
    for data in (
        payload(day="2026-10-04"),
        payload(symbol="OTHER"),
        {"Information": "API quota message with secret"},
    ):
        with pytest.raises(MarketDataError):
            parse_daily(data, "EX", date(2026, 10, 3))


@pytest.mark.asyncio
async def test_provider_preserves_source_without_leaking_key(caplog):
    secret = "private-test-key"

    def handler(request):
        assert request.url.params["apikey"] == secret
        assert request.url.params["outputsize"] == "compact"
        return httpx.Response(200, json=payload())

    with caplog.at_level(logging.INFO, logger="httpx"):
        rows, url = await AlphaVantageClient(secret, transport=httpx.MockTransport(handler)).daily(
            "EX"
        )
    assert rows and "EX" in url
    assert secret not in url and secret not in caplog.text
    assert "apikey" not in url


@pytest.mark.asyncio
async def test_provider_errors_never_include_request_url_or_secret():
    client = AlphaVantageClient(
        "secret-token", transport=httpx.MockTransport(lambda r: httpx.Response(403))
    )
    with pytest.raises(MarketDataError) as error:
        await client.daily("EX")
    assert str(error.value) == "provider_http_error"
    assert "secret-token" not in str(error.value)


def test_buy_and_partial_then_full_sale_allocate_costs_and_fees():
    buy = calculate_fill(
        cash=Decimal("10000"),
        held=0,
        cost_basis=Decimal("0"),
        side="buy",
        quantity=10,
        price=Decimal("100"),
        fee_bps=Decimal("10"),
    )
    assert (buy.cash, buy.quantity, buy.cost_basis, buy.fee) == (
        Decimal("8999"),
        10,
        Decimal("1001"),
        Decimal("1"),
    )
    first = calculate_fill(
        cash=buy.cash,
        held=buy.quantity,
        cost_basis=buy.cost_basis,
        side="sell",
        quantity=3,
        price=Decimal("120"),
        fee_bps=Decimal("10"),
    )
    assert first.cost_basis == Decimal("700.70") and first.realized_pnl == Decimal("59.34")
    last = calculate_fill(
        cash=first.cash,
        held=first.quantity,
        cost_basis=first.cost_basis,
        side="sell",
        quantity=7,
        price=Decimal("120"),
        fee_bps=Decimal("10"),
    )
    assert last.quantity == 0 and last.cost_basis == 0
    assert last.cash - Decimal("10000") == first.realized_pnl + last.realized_pnl


def test_insufficient_cash_and_short_sales_are_blocked():
    with pytest.raises(ValueError, match="centime"):
        calculate_fill(
            cash=Decimal("100"),
            held=0,
            cost_basis=Decimal("0"),
            side="buy",
            quantity=1,
            price=Decimal("0.000001"),
            fee_bps=Decimal("0"),
        )
    with pytest.raises(ValueError, match="frais inclus"):
        calculate_fill(
            cash=Decimal("100"),
            held=0,
            cost_basis=Decimal("0"),
            side="buy",
            quantity=1,
            price=Decimal("100"),
            fee_bps=Decimal("10"),
        )
    with pytest.raises(ValueError, match="découvert"):
        calculate_fill(
            cash=Decimal("100"),
            held=1,
            cost_basis=Decimal("50"),
            side="sell",
            quantity=2,
            price=Decimal("100"),
            fee_bps=Decimal("0"),
        )


def test_position_limit_uses_portfolio_value_and_rejects_excess():
    check_concentration(Decimal("2500"), Decimal("10000"), Decimal("25"))
    with pytest.raises(ValueError):
        check_concentration(Decimal("2500.01"), Decimal("10000"), Decimal("25"))


def test_rules_validate_currency_dates_allowed_symbols_and_precision():
    rules = PortfolioCreate(name="Challenge", allowed_symbols=[" ex ", "EX"])
    assert rules.allowed_symbols == ["EX"]
    for values in (
        {"initial_capital": "0"},
        {"initial_capital": "100.001"},
        {"currency": "EUR"},
        {"starts_on": "2026-10-03", "ends_on": "2026-10-01"},
        {"max_position_pct": 101},
    ):
        with pytest.raises(ValidationError):
            PortfolioCreate(name="Challenge", **values)
    assert not Settings(alpha_vantage_api_key="").alpha_vantage_api_key.get_secret_value()


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_paper_order_requires_positive_whole_quantities(quantity):
    with pytest.raises(ValidationError):
        PaperOrder(instrument_id=uuid4(), client_order_id=uuid4(), side="buy", quantity=quantity)
