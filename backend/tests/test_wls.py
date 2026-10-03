from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.market.wls import eligibility, parse_wls_csv
from app.schemas.market import PortfolioCreate

HEADER = "security_id,symbol,exchange,asset_class\n"


def test_company_share_classes_are_separate_securities():
    rows = parse_wls_csv(
        HEADER + "id-a,EX.A,NYSE,equity\nid-b,EX.B,NYSE,equity\n", date(2026, 10, 3)
    )
    assert len(rows) == 2
    registry = SimpleNamespace(records=rows, source_url="https://example.com/wls")
    a = SimpleNamespace(symbol="EX.A", exchange="NYSE", cik="0000000001")
    b = SimpleNamespace(symbol="EX.B", exchange="NYSE", cik="0000000001")
    assert eligibility(a, registry)["security_id"] != eligibility(b, registry)["security_id"]
    only_a = SimpleNamespace(records=rows[:1], source_url=registry.source_url)
    assert eligibility(b, only_a)["status"] == "not_verified"
    assert eligibility(a, None)["status"] == "unknown"


def test_membership_does_not_follow_a_ticker_to_another_venue():
    rows = parse_wls_csv(HEADER + "id-a,EX,NYSE,equity\n", date(2026, 10, 3))
    registry = SimpleNamespace(records=rows, source_url="https://example.com/wls")
    assert (
        eligibility(SimpleNamespace(symbol="EX", exchange="Nasdaq"), registry)["status"]
        == "not_verified"
    )


@pytest.mark.parametrize(
    "body",
    [
        "",
        "id-a,EX,NYSE,etf\n",
        "id-a,EX,NYSE,future\n",
        "id-a,EX,NYSE,equity\nid-a,OTHER,Nasdaq,equity\n",
        "id-a,EX,NYSE,equity\nid-b,EX,NYSE,equity\n",
    ],
)
def test_empty_duplicate_and_non_stock_universes_are_rejected(body):
    with pytest.raises(ValueError):
        parse_wls_csv(HEADER + body, date(2026, 10, 3))


def test_challenge_default_capital_is_one_million_usd():
    rules = PortfolioCreate(name="Challenge")
    assert rules.initial_capital == Decimal("1000000") and rules.currency == "USD"
