import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.market.openfigi import MIC_EXCHANGE_CODES, FigiError, OpenFigiClient, parse_job
from app.schemas.market import PortfolioCreate
from app.services.wls_automation import assess_listing, identity_job, venue_jobs


def record(**changes):
    return {
        "figi": "BBG000B9XRY4",
        "ticker": "AAPL",
        "name": "Apple fixture",
        "exchCode": "US",
        "compositeFIGI": "BBG000B9XRY4",
        "shareClassFIGI": "BBG001S5N8V8",
        "marketSector": "Equity",
        "securityType": "Common Stock",
        "securityType2": "Common Stock",
    } | changes


def setup_evidence(exchange="NYSE"):
    instrument = SimpleNamespace(
        id=uuid4(), symbol="AAPL", exchange=exchange, currency="USD", bloomberg_symbol=None
    )
    row = {
        "bloomberg_identifier": "AAPL US Equity",
        "bloomberg_ticker": "AAPL",
        "bloomberg_market_code": "US",
    }
    manifest = {"source_sha256": "a" * 64, "composition_as_of": None, "records": [row]}
    now = datetime.now(UTC)
    identity = SimpleNamespace(
        id=uuid4(),
        observed_at=now,
        query=identity_job(row),
        status="resolved",
        data=parse_job({"data": [record()]}),
    )
    observations = {(row["bloomberg_identifier"], "identity"): identity}
    for key, query in venue_jobs(instrument, row, identity):
        observations[(row["bloomberg_identifier"], key)] = SimpleNamespace(
            id=uuid4(),
            observed_at=now,
            query=query,
            status="resolved",
            data=parse_job(
                {
                    "data": [
                        record(figi="BBG000B9Y5X2", exchCode=MIC_EXCHANGE_CODES[query["micCode"]])
                    ]
                }
            ),
        )
    return instrument, manifest, observations, now


def test_figi_composite_is_not_a_listing_proof():
    instrument, manifest, observations, now = setup_evidence()
    del observations[next(k for k in observations if k[1] != "identity")]
    assert assess_listing(instrument, manifest, observations, now)["status"] == "unresolved"


def test_matching_composite_share_class_and_exact_mic_enable_only_provisional_preparation():
    instrument, manifest, observations, now = setup_evidence()
    result = assess_listing(instrument, manifest, observations, now)
    assert result["status"] == "matched"
    assert result["evidence"]["composition_as_of"] is None
    assert len(result["evidence"]["observations"]) == 2
    assert PortfolioCreate(name="Strict").wls_policy == "verified"


@pytest.mark.parametrize(
    "change",
    [
        {"ticker": "OTHER"},
        {"compositeFIGI": "BBG000BCY2S8"},
        {"shareClassFIGI": "BBG001S6K037"},
        {"securityType": "Depositary Receipt"},
        {"securityType": "ETP"},
        {"marketSector": "Corp"},
        {"securityType2": "Depositary Receipt"},
        {"exchCode": "UW"},
    ],
)
def test_venue_mismatch_or_non_common_stock_is_blocked(change):
    instrument, manifest, observations, now = setup_evidence()
    venue = next(o for (_, key), o in observations.items() if key != "identity")
    venue.data["records"][0].update(change)
    assert assess_listing(instrument, manifest, observations, now)["status"] == "unresolved"


def test_nasdaq_checks_all_segments_and_preserves_ambiguity():
    instrument, manifest, observations, now = setup_evidence("Nasdaq")
    venues = [o for (_, key), o in observations.items() if key != "identity"]
    assert len(venues) == 3
    venues[-1].data["records"][0]["figi"] = "BBG000BCY2S8"
    assert assess_listing(instrument, manifest, observations, now)["status"] == "unresolved"
    venues[-1].status = "not_found"
    venues[-1].data = {"records": []}
    assert assess_listing(instrument, manifest, observations, now)["status"] == "matched"
    venues[-1].status = "running"
    assert assess_listing(instrument, manifest, observations, now)["status"] == "unresolved"


def test_stale_changed_query_or_missing_class_proof_cannot_be_reused():
    instrument, manifest, observations, now = setup_evidence()
    identity = observations[("AAPL US Equity", "identity")]
    identity.observed_at = now - timedelta(days=8)
    assert assess_listing(instrument, manifest, observations, now)["status"] == "unresolved"
    identity.observed_at = now
    identity.query["exchCode"] = "HK"
    assert assess_listing(instrument, manifest, observations, now)["status"] == "unresolved"


def test_multiple_figis_are_not_selected_arbitrarily_and_errors_are_sanitized():
    parsed = parse_job({"data": [record(), record(figi="BBG000BCY2S8")]})
    assert parsed["status"] == "ambiguous"
    assert parse_job({"error": "provider private details"}) == {
        "status": "provider_error",
        "records": [],
    }
    assert parse_job({"warning": "No identifier found."})["status"] == "not_found"


@pytest.mark.asyncio
async def test_mapping_client_uses_five_jobs_max_and_exact_payload():
    query = {"idType": "TICKER", "idValue": "AAPL", "exchCode": "US"}

    def respond(request):
        assert json.loads(request.content) == [query]
        assert request.url == "https://api.openfigi.com/v3/mapping"
        return httpx.Response(200, json=[{"data": [record()]}])

    client = OpenFigiClient(httpx.MockTransport(respond))
    assert (await client.fetch([query]))[0]["status"] == "resolved"
    with pytest.raises(ValueError):
        await client.fetch([query] * 6)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(200, json=[]), "invalid_response"),
        (httpx.Response(200, json=[{"data": [{"figi": "BAD"}]}]), "invalid_response"),
        (httpx.Response(429, headers={"ratelimit-reset": "90"}), "quota"),
        (httpx.Response(503, text="provider details"), "http_error"),
        (httpx.Response(200, content=b"x" * 1_000_001), "response_too_large"),
    ],
)
async def test_mapping_provider_failures_are_bounded(response, code):
    client = OpenFigiClient(httpx.MockTransport(lambda request: response))
    with pytest.raises(FigiError) as error:
        await client.fetch([{"idType": "TICKER", "idValue": "AAPL"}])
    assert error.value.code == code
