import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.collectors.company_sec import CompanyPublicationError
from app.market.sec_financials import FinancialRecord, SecFinancialClient, parse_financials
from app.services.financial_results import eps_comparison_guard

TODAY = datetime.now(UTC).date()


def row(**changes):
    return {
        "start": str(TODAY - timedelta(days=100)),
        "end": str(TODAY - timedelta(days=10)),
        "filed": str(TODAY - timedelta(days=1)),
        "val": 0,
        "accn": "0000320193-26-000001",
        "form": "10-Q",
        "fy": 2026,
        "fp": "Q3",
        **changes,
    }


def payload(rows=None, concept="EarningsPerShareDiluted", unit="USD/shares"):
    return {"cik": 320193, "facts": {"us-gaap": {concept: {"units": {unit: rows or [row()]}}}}}


def parse(data):
    return parse_financials(json.dumps(data).encode(), "0000320193")


def test_exact_values_zero_losses_periods_and_issuer_eps_guard():
    records = parse(payload([row(val=-1.234567), row(val=0, accn="0000320193-26-000002")]))
    assert {record.value for record in records} == {Decimal("-1.234567"), Decimal("0")}
    assert all(record.filing_period == "Q3" for record in records)
    assert eps_comparison_guard(records[0].model_dump(mode="json"))["status"] == "not_comparable"


def test_cumulative_periods_republications_and_revenue_definitions_stay_separate():
    data = payload(
        [
            row(val=100),
            row(val=200, start=str(TODAY - timedelta(days=270))),
            row(val=110, accn="0000320193-26-000002"),
        ],
        "Revenues",
        "USD",
    )
    data["facts"]["us-gaap"]["SalesRevenueNet"] = {"units": {"USD": [row(val=100)]}}
    records = parse(data)
    assert len(records) == 4
    assert {record.concept for record in records} == {"Revenues", "SalesRevenueNet"}
    assert len({record.start for record in records}) == 2
    assert eps_comparison_guard(records[0].model_dump(mode="json")) is None


def test_duplicate_rows_are_idempotent_without_selecting_a_latest_value():
    assert len(parse(payload([row(), row()]))) == 1
    assert len(parse(payload([row(val=1), row(val=2)]))) == 2


def test_cash_and_debt_are_instants_without_invented_start_dates():
    instant = row(val=100)
    instant.pop("start")
    data = payload([instant], "CashAndCashEquivalentsAtCarryingValue", "USD")
    data["facts"]["us-gaap"]["LongTermDebtCurrent"] = {"units": {"USD": [instant]}}
    data["facts"]["us-gaap"]["LongTermDebtNoncurrent"] = {"units": {"USD": [instant]}}
    records = parse(data)
    assert len(records) == 3
    assert all(record.start is None for record in records)
    assert {record.metric for record in records} == {"cash", "debt_current", "debt_noncurrent"}


def test_wrong_instant_duration_or_negative_balance_rejects_batch():
    for concept, changes in [
        ("CashAndCashEquivalentsAtCarryingValue", {}),
        ("LongTermDebtCurrent", {"start": None, "val": -1}),
        ("NetCashProvidedByUsedInOperatingActivities", {"start": None}),
    ]:
        with pytest.raises(CompanyPublicationError):
            parse(payload([row(**changes)], concept, "USD"))


def test_cash_flows_keep_negative_values_and_exact_cumulative_periods():
    records = parse(
        payload([row(val=-100), row(val=0)], "NetCashProvidedByUsedInOperatingActivities", "USD")
    )
    assert len(records) == 2
    assert all(record.metric == "operating_cash_flow" and record.start for record in records)
    assert {record.value for record in records} == {Decimal("-100"), Decimal("0")}


@pytest.mark.parametrize(
    "changes",
    [
        {"val": "NaN"},
        {"val": "Infinity"},
        {"val": True},
        {"val": "1.12345678901"},
        {"start": str(TODAY)},
        {"accn": "bad"},
        {"fy": "2026"},
    ],
)
def test_invalid_last_selected_row_rejects_entire_batch(changes):
    with pytest.raises(CompanyPublicationError):
        parse(payload([row(), row(**changes)]))


def test_unsupported_taxonomies_units_and_future_rows_do_not_invent_values():
    assert parse(payload(unit="USD")) == []
    assert parse(payload(unit="BAD/shares")) == []
    assert parse({"cik": 320193, "facts": {"ifrs-full": {"ProfitLoss": {}}}}) == []
    assert parse(payload([row(filed=str(TODAY + timedelta(days=1)))])) == []
    assert (
        parse(
            payload(
                [row(end=str(TODAY - timedelta(days=731)), start=str(TODAY - timedelta(days=800)))]
            )
        )
        == []
    )


def test_identity_and_metadata_required():
    data = payload()
    data["cik"] = 1
    with pytest.raises(CompanyPublicationError, match="sec_identity_mismatch"):
        parse(data)
    with pytest.raises(CompanyPublicationError):
        parse_financials(b"{}", "0000320193")
    data = payload()
    del data["facts"]["us-gaap"]["EarningsPerShareDiluted"]["units"]["USD/shares"][0]["start"]
    with pytest.raises(CompanyPublicationError):
        parse(data)


def test_revalidate_constructed_or_mutated_records_before_writing():
    record = parse(payload())[0].model_copy(update={"value": Decimal("NaN")})
    with pytest.raises(ValidationError):
        FinancialRecord.model_validate(record.model_dump())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected", [(403, "sec_http_error"), (302, "sec_http_error"), (429, "sec_rate_limit")]
)
async def test_http_errors_do_not_follow_redirects_or_retain_response(status, expected):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            status, text="secret-provider-body", headers={"Location": "https://evil.example"}
        )

    client = SecFinancialClient(
        "0000320193", "Fixture test@example.org", transport=httpx.MockTransport(respond)
    )
    with pytest.raises(CompanyPublicationError) as error:
        await client.fetch()
    assert error.value.code == expected and len(calls) == 1


@pytest.mark.asyncio
async def test_http_success_and_size_bound():
    client = SecFinancialClient(
        "0000320193",
        "Fixture test@example.org",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload())),
    )
    assert len(await client.fetch()) == 1
    client.transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 12_000_001)
    )
    with pytest.raises(CompanyPublicationError, match="sec_response_too_large"):
        await client.fetch()
