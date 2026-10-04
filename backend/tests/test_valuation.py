from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from app.schemas.valuation import ValuationInput
from app.services.valuation import calculate_valuation, security_identity

NOW = datetime.now(UTC)
SESSION = NOW.date() - timedelta(days=2)
END = SESSION - timedelta(days=90)


def payload(**changes):
    return {
        "valuation_date": SESSION.isoformat(),
        "currency": "USD",
        "quote_multiplier": "1",
        "period_start": (END - timedelta(days=364)).isoformat(),
        "period_end": END.isoformat(),
        "period_type": "annual",
        "basis": "gaap_diluted",
        "eps_per_security": "5",
        "source_url": "https://example.org/annual",
        "published_at": datetime.combine(
            END + timedelta(days=30), datetime.min.time(), UTC
        ).isoformat(),
        "security_basis_confirmed": True,
        "security_basis_note": "Exact share class and split conventions documented in source.",
        "security_source_url": "https://example.org/security",
        "security_published_at": datetime.combine(
            SESSION - timedelta(days=1), datetime.min.time(), UTC
        ).isoformat(),
        "reference": None,
        **changes,
    }


def instrument(**changes):
    return NS(
        symbol="TEST",
        exchange="NYSE",
        cik="0000000001",
        isin=None,
        currency=changes.get("currency", "USD"),
        quote_multiplier=Decimal(changes.get("quote_multiplier", "1")),
    )


def price(**changes):
    return NS(
        session_date=changes.get("session_date", SESSION),
        close=Decimal(changes.get("close", "100")),
        quote_context=changes.get("quote_context"),
    )


def calculate(data=None, listing=None, quote=None):
    listing = listing or instrument()
    data = payload() if data is None else data
    return calculate_valuation(
        listing, quote or price(), {**data, "security_identity": security_identity(listing)}, NOW
    )


def test_per_and_accounting_yield_do_not_claim_expected_return():
    result = calculate()
    assert result["status"] == "available"
    assert result["pe"] == "20.00"
    assert result["earnings_yield_percent"] == "5.00"
    assert result["reference_comparison"] is None


def test_reference_is_explicit_dated_and_higher_lower_is_not_intrinsic_value():
    data = payload(
        reference={
            "value": "25",
            "label": "Documented peers",
            "rationale": "Same annual GAAP diluted basis and comparable activity.",
            "basis": "annual_gaap_diluted",
            "as_of": (SESSION - timedelta(days=1)).isoformat(),
            "source_url": "https://example.org/peers",
            "published_at": payload()["security_published_at"],
        }
    )
    result = calculate(data)["reference_comparison"]
    assert result["position"] == "lower"
    assert result["difference_percent"] == "-20.00"
    assert "signal d’achat" in result["notice"]


@pytest.mark.parametrize(
    "changes",
    [
        {"security_basis_confirmed": False},
        {"period_type": "quarterly"},
        {"basis": "adjusted_diluted"},
        {"period_start": (END - timedelta(days=89)).isoformat()},
        {"eps_per_security": "NaN"},
        {"published_at": datetime.combine(SESSION, datetime.min.time(), UTC).isoformat()},
        {"published_at": "2026-01-01T00:00:00"},
        {"source_url": "https://example.org/api?apikey=secret"},
        {"security_basis_note": "unknown"},
    ],
)
def test_unverified_and_incompatible_inputs_are_rejected(changes):
    with pytest.raises(ValidationError):
        ValuationInput.model_validate(payload(**changes))


@pytest.mark.parametrize("eps", ["0", "-5"])
def test_non_positive_earnings_are_preserved_but_per_is_blocked(eps):
    result = calculate(payload(eps_per_security=eps))
    assert result["status"] == "blocked"
    assert result["pe"] is None


def test_local_quote_units_are_normalized_without_fx_or_invented_adr_ratio():
    result = calculate(
        payload(currency="GBP", quote_multiplier="0.01", eps_per_security="2"),
        instrument(currency="GBP", quote_multiplier="0.01"),
        price(close="1000"),
    )
    assert result["pe"] == "5.00"
    assert result["normalized_price"] == "10.00"


def test_price_session_units_currency_and_adjusted_context_are_controlled():
    for data, quote in [
        (payload(currency="EUR"), price()),
        (payload(quote_multiplier="0.01"), price()),
        (payload(), price(session_date=SESSION - timedelta(days=1))),
        (payload(), price(session_date=NOW.date() - timedelta(days=100))),
        (payload(), price(quote_context={"adjusted": True})),
        (payload(), price(quote_context={"symbol": "OTHER"})),
        (payload(), price(close="NaN")),
        (payload(), price(quote_context={"quote_multiplier": "invalid"})),
    ]:
        assert calculate(data, quote=quote)["status"] == "blocked"


def test_missing_evidence_or_changed_security_identity_never_uses_issuer_eps():
    assert calculate_valuation(instrument(), price(), None, NOW)["pe"] is None
    data = {**payload(), "security_identity": {"symbol": "OTHER"}}
    assert calculate_valuation(instrument(), price(), data, NOW)["status"] == "blocked"
    assert (
        calculate_valuation(
            instrument(),
            None,
            {**payload(), "security_identity": security_identity(instrument())},
            NOW,
        )["status"]
        == "blocked"
    )


def test_very_small_positive_multiple_is_not_displayed_as_zero():
    assert (
        Decimal(calculate(payload(eps_per_security="99999"), quote=price(close="0.000001"))["pe"])
        > 0
    )
