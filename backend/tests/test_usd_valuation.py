from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.market.wls import parse_wls_csv
from app.schemas.international import FxRateCreate, InternationalInstrumentCreate, LocalPriceCreate
from app.services.instrument_research import relationship
from app.services.usd_valuation import UsdValuationService, converted_price


def identity(**changes):
    return InternationalInstrumentCreate.model_validate(
        {
            "symbol": "2600",
            "exchange": "XHKG",
            "name": "Fixture only",
            "isin": "US0378331005",
            "currency": "HKD",
            "quote_multiplier": "1",
            "asset_class": "equity",
            "source_url": "https://example.org/identity",
            "as_of": "2026-01-01",
            **changes,
        }
    )


def test_identifiers_and_wls_accept_numeric_tickers_without_guessing():
    assert identity().symbol == "2600"
    assert identity(exchange="XPAR").exchange == "XPAR"
    rows = parse_wls_csv(
        "security_id,symbol,exchange,asset_class\nid,2600,XHKG,equity", date(2026, 1, 1)
    )
    assert rows[0]["symbol"] == "2600"


@pytest.mark.parametrize(
    "changes",
    [
        {"isin": "US0378331004"},
        {"asset_class": "forex"},
        {"asset_class": "etf"},
        {"currency": "BTC"},
        {"quote_multiplier": "0"},
        {"exchange": "XNAS"},
        {"source_url": "https://example.org/?apikey=secret"},
        {"source_url": "https://user:secret@example.org/"},
        {"as_of": "2999-01-01"},
    ],
)
def test_invalid_identity_is_rejected(changes):
    with pytest.raises(ValidationError):
        identity(**changes)


def test_fx_direction_and_price_units_are_explicit():
    assert converted_price(Decimal("1000"), Decimal("0.01"), Decimal("1.25")) == Decimal(
        "12.500000"
    )
    assert converted_price(Decimal("100"), Decimal("1"), Decimal("0.128")) == Decimal("12.800000")
    with pytest.raises(ValidationError):
        FxRateCreate(
            currency="USD", usd_per_unit="1", as_of="2026-01-01", source_url="https://example.org"
        )
    with pytest.raises(ValidationError):
        LocalPriceCreate(
            currency="JPY",
            quote_multiplier="1",
            close="NaN",
            volume=1,
            as_of="2026-01-01",
            source_url="https://example.org",
        )


@pytest.mark.parametrize(
    "close,rate",
    [("NaN", "1"), ("1", "-1"), ("0.000001", "0.0000000001"), ("99999999999999", "9999999999")],
)
def test_bad_or_unrepresentable_usd_price_is_rejected(close, rate):
    with pytest.raises(ValueError):
        converted_price(Decimal(close), Decimal("1"), Decimal(rate))


@pytest.mark.asyncio
async def test_fx_missing_stale_and_usd_identity():
    today = date(2026, 1, 10)
    price = NS(
        close=Decimal("100"),
        session_date=today,
        source_url="https://example.org/price",
        fetched_at=NS(isoformat=lambda: "2026-01-10T00:00:00+00:00"),
    )
    instrument = NS(currency="HKD", quote_multiplier=Decimal("1"))
    session = NS(execute=AsyncMock(return_value=NS(scalar_one_or_none=lambda: None)))
    service = UsdValuationService(session)
    assert (await service.quote(instrument, price, today))["status"] == "missing_fx"
    rate = NS(
        usd_per_unit=Decimal("0.128"),
        rate_date=today - timedelta(days=8),
        source_url="https://example.org/fx",
        fetched_at=price.fetched_at,
    )
    session.execute.return_value = NS(scalar_one_or_none=lambda: rate)
    result = await service.quote(instrument, price, today)
    assert result["price_usd"] == Decimal("12.800000") and result["stale"]
    assert result["conversion"]["fx_date"] == rate.rate_date.isoformat()
    instrument.currency = "USD"
    session.execute.reset_mock()
    assert (await service.quote(instrument, price, today))["price_usd"] == Decimal("100")
    session.execute.assert_not_called()


def test_missing_cik_never_matches_other_unknown_issuers():
    assert relationship(NS(), NS(cik=None)) is None
