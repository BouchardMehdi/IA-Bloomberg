from unittest.mock import AsyncMock

import httpx
import pytest

from app.entities.resolver import EntityResolver, parse_registry
from app.services.entity_resolution import EntityResolutionService


def registry():
    return [
        {"cik": "0000000001", "name": "Example Inc.", "ticker": "EX", "exchange": "NYSE"},
        {"cik": "0000000001", "name": "Example Inc.", "ticker": "EX.A", "exchange": "NYSE"},
        {"cik": "0000000002", "name": "Other Corp", "ticker": "OT", "exchange": "Nasdaq"},
    ]


def test_names_and_filing_aliases_resolve_to_stable_cik_and_multiple_listings():
    resolver = EntityResolver(registry(), [{"cik": "0000000001", "name": "Example Incorporated"}])
    result = resolver.resolve(
        "Example Incorporated",
        "company",
        "subject",
        "Example Incorporated acquired Other Corp.",
        "Example Incorporated acquired Other Corp.",
    )
    assert result["status"] == "resolved"
    assert result["candidates"][0]["cik"] == "0000000001"
    assert len(result["candidates"][0]["listings"]) == 2


def test_colliding_names_and_tickers_preserve_all_candidates():
    rows = registry() + [
        {"cik": "0000000003", "name": "Example, Inc", "ticker": "EX", "exchange": "Other venue"}
    ]
    resolver = EntityResolver(rows)
    name = resolver.resolve("Example Inc", "company", "mention", "Example Inc", "Example Inc")
    ticker = resolver.resolve("EX", "equity", "mention", "EX shares", "EX shares")
    assert name["status"] == ticker["status"] == "ambiguous"
    assert len(name["candidates"]) == len(ticker["candidates"]) == 2


@pytest.mark.parametrize(
    "name,quote,text",
    [
        ("Example Inc.", "Example Inc. acquired Other Corp.", "No acquisition happened."),
        ("EX", "A complex filing", "A complex filing"),
        ("Other Corp", "Example Inc. announced a deal", "Example Inc. announced a deal"),
    ],
)
def test_hallucinated_or_substring_mentions_are_unverified(name, quote, text):
    result = EntityResolver(registry()).resolve(name, "company", "subject", quote, text)
    assert result["status"] == "unverified" and result["role"] == "mention"
    assert result["candidates"] == []


def test_unknown_names_are_not_fuzzily_matched_and_bonds_remain_unresolved():
    resolver = EntityResolver(registry())
    assert (
        resolver.resolve("Example", "company", "mention", "Example", "Example")["status"]
        == "unresolved"
    )
    assert (
        resolver.resolve("Example bond", "bond", "mention", "Example bond", "Example bond")[
            "status"
        ]
        == "unresolved"
    )


def test_currency_requires_an_explicit_supported_code_and_tickers_are_case_sensitive():
    resolver = EntityResolver(registry())
    assert (
        resolver.resolve("EX", "equity", "mention", "ex ante", "ex ante")["status"] == "unverified"
    )
    assert (
        resolver.resolve("USD", "currency", "mention", "100 USD", "100 USD")["status"] == "resolved"
    )
    assert resolver.resolve("$", "currency", "mention", "$100", "$100")["status"] != "resolved"
    assert (
        resolver.resolve("ex", "equity", "mention", "ex shares", "ex shares")["status"]
        == "unresolved"
    )


def test_legacy_fact_is_reused_without_inventing_roles_or_matching_unquoted_names():
    fact = {
        "companies": ["Example Inc.", "Other Corp"],
        "assets": ["USD"],
        "evidence": [{"quote": "Example Inc. approved 100 USD."}],
    }
    result = EntityResolver(registry()).resolve_fact(fact, "Example Inc. approved 100 USD.")
    assert [r["status"] for r in result] == ["resolved", "unverified", "resolved"]
    assert all(r["role"] == "mention" for r in result)


def test_role_mentions_require_their_own_verbatim_quote():
    quote = "Example Inc. acquired Other Corp."
    result = EntityResolver(registry()).resolve_fact(
        {
            "entity_mentions": [
                {"name": "Example Inc.", "kind": "company", "role": "subject", "quote": quote},
                {"name": "Other Corp", "kind": "company", "role": "counterparty", "quote": quote},
            ]
        },
        quote,
    )
    assert [r["role"] for r in result] == ["subject", "counterparty"]
    assert all(r["status"] == "resolved" for r in result)


def test_sec_registry_validation_handles_field_order_and_leading_zeroes():
    records = parse_registry(
        {"fields": ["name", "exchange", "cik", "ticker"], "data": [["Example Inc", None, 1, "EX"]]}
    )
    assert records[0]["cik"] == "0000000001"
    for payload in (
        {"fields": [], "data": []},
        {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [["invalid", "Example", "EX", "NYSE"]],
        },
    ):
        with pytest.raises(ValueError):
            parse_registry(payload)


@pytest.mark.asyncio
async def test_registry_http_or_validation_failure_cannot_replace_previous_snapshot():
    for response in (httpx.Response(403), httpx.Response(200, json={"fields": [], "data": []})):
        session = AsyncMock()
        session.get.return_value = None
        service = EntityResolutionService(session)
        with pytest.raises((httpx.HTTPStatusError, ValueError)):
            await service.sync_registry(
                "MarketAI test", transport=httpx.MockTransport(lambda r, result=response: result)
            )
        session.execute.assert_not_awaited()
        session.commit.assert_not_awaited()
