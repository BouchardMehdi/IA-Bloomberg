from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.market.alpha_vantage import AlphaVantageClient
from app.market.providers import QuoteIdentity
from app.schemas.portfolio_tracking import CorporateActionInput, PriceMappingInput
from app.services.portfolio_actions import entitled_quantity, split_quantity


def action(**overrides):
    today = datetime.now(UTC).date()
    return (
        dict(
            kind="dividend",
            effective_date=today,
            payment_date=today,
            currency="USD",
            net_amount_per_security="1.25",
            source_url="https://example.org/dividend",
            published_at=datetime.now(UTC) - timedelta(days=2),
            confirmed=True,
            note="Dividende net explicitement documenté par titre.",
        )
        | overrides
    )


@pytest.mark.parametrize(
    "override",
    [
        {"confirmed": False},
        {"source_url": "https://example.org/source?apikey=secret"},
        {"published_at": datetime.now()},
        {"net_amount_per_security": "0"},
        {"numerator": 2},
        {"payment_date": datetime.now(UTC).date() + timedelta(days=1)},
        {"payment_date": datetime.now(UTC).date() - timedelta(days=1)},
    ],
)
def test_invalid_action_conventions(override):
    with pytest.raises(ValidationError):
        CorporateActionInput(**action(**override))


def test_split_does_not_create_fraction_or_silent_cash():
    assert split_quantity(5, 2, 1) == 10
    assert split_quantity(10, 1, 2) == 5
    with pytest.raises(ValueError, match="fraction"):
        split_quantity(5, 1, 2)
    with pytest.raises(ValueError):
        split_quantity(2_000_000_000, 2, 1)


def test_entitlements_use_execution_not_old_quote_date_and_include_prior_splits():
    now = datetime.now(UTC)
    ex = now.date()
    buy = SimpleNamespace(executed_at=now - timedelta(days=3), quantity=10, side="buy")
    sell = SimpleNamespace(executed_at=now - timedelta(days=1), quantity=3, side="sell")
    today_buy = SimpleNamespace(executed_at=now, quantity=100, side="buy")
    split = SimpleNamespace(
        kind="split",
        effective_date=ex - timedelta(days=2),
        data={"request": {"numerator": 2, "denominator": 1}},
    )
    assert entitled_quantity([sell, today_buy, buy], [split], ex) == 17


def mapping(identity):
    return PriceMappingInput(
        **identity.model_dump(),
        provider_symbol="EX.LON",
        source_url="https://example.org/provider-listing",
        published_at=datetime.now(UTC) - timedelta(days=2),
        as_of=datetime.now(UTC).date(),
        confirmed=True,
        note="Preuve explicite du MIC, de la devise et de l’unité pence.",
    )


@pytest.mark.asyncio
async def test_international_mapping_is_explicit_exact_and_preserved():
    identity = QuoteIdentity(
        instrument_id=uuid4(),
        symbol="EX",
        exchange="XLON",
        currency="GBP",
        quote_multiplier="0.010000",
    )
    calls = []

    def respond(request):
        calls.append(request.url.params["symbol"])
        return httpx.Response(
            200,
            json={
                "Meta Data": {"2. Symbol": "EX.LON"},
                "Time Series (Daily)": {
                    datetime.now(UTC).date().isoformat(): {"4. close": "123.45", "5. volume": "50"}
                },
            },
        )

    provider = AlphaVantageClient("fixture", transport=httpx.MockTransport(respond))
    assert not provider.supports(identity)
    provider.mappings[str(identity.instrument_id)] = mapping(identity).model_dump(mode="json")
    assert provider.supports(identity)
    assert not provider.supports(identity.model_copy(update={"currency": "USD"}))
    batch = await provider.fetch(identity)
    assert calls == ["EX.LON"]
    assert batch.identity == identity
    assert (
        batch.context()["mapping_evidence"]["source_url"] == "https://example.org/provider-listing"
    )
    assert "fixture" not in str(batch.source_url)
