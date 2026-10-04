import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.collectors.company_sec import FORMS, CompanyPublicationError, SECCompanyCollector
from app.repositories.events import parse_sec_filing_title

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def payload(forms=None):
    forms = forms or ["10-Q", "8-K", "10-K"]
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "form": forms,
                "accessionNumber": [f"0000320193-26-{i:06d}" for i in range(len(forms))],
                "acceptanceDateTime": [
                    (NOW - timedelta(days=i + 1)).isoformat() for i in range(len(forms))
                ],
                "primaryDocument": [f"aapl-{i}.htm" for i in range(len(forms))],
            }
        },
    }


def collector():
    return SECCompanyCollector("0000320193", "MarketAI fixture@example.org", now=NOW)


def test_supported_forms_have_verified_issuer_context():
    articles = collector().normalize(json.dumps(payload(sorted(FORMS))).encode())
    assert len(articles) == len(FORMS)
    for article in articles:
        identity = parse_sec_filing_title(article.title)
        assert identity.cik == "0000320193"
        assert identity.form in FORMS
        assert article.published_at < NOW
        assert article.url.startswith("https://www.sec.gov/Archives/edgar/data/320193/")
        assert "accession-number=" in article.external_id


def test_only_bounded_supported_nonfuture_history_is_selected():
    data = payload(["144", "8-K", "10-K", "6-K"])
    data["filings"]["recent"]["acceptanceDateTime"][1] = (NOW + timedelta(days=1)).isoformat()
    data["filings"]["recent"]["acceptanceDateTime"][2] = (NOW - timedelta(days=366)).isoformat()
    assert len(collector().normalize(json.dumps(data).encode())) == 1
    assert len(collector().normalize(json.dumps(payload(["8-K"] * 60)).encode())) == 50


@pytest.mark.parametrize(
    "field,value",
    [
        ("primaryDocument", "../secret.htm"),
        ("primaryDocument", "https://evil.example/file.htm"),
        ("primaryDocument", "%2e%2e.htm"),
        ("primaryDocument", "dir/file.htm"),
        ("accessionNumber", "invalid"),
        ("acceptanceDateTime", "2026-10-01T12:00:00"),
    ],
)
def test_bad_metadata_rejects_complete_batch(field, value):
    data = payload()
    data["filings"]["recent"][field][-1] = value
    with pytest.raises(CompanyPublicationError, match="sec_invalid_response"):
        collector().normalize(json.dumps(data).encode())


def test_identity_and_array_lengths_checked():
    data = payload()
    data["cik"] = "1"
    with pytest.raises(CompanyPublicationError, match="sec_identity_mismatch"):
        collector().normalize(json.dumps(data).encode())
    data = payload()
    data["filings"]["recent"]["primaryDocument"].pop()
    with pytest.raises(CompanyPublicationError):
        collector().normalize(json.dumps(data).encode())
    with pytest.raises(CompanyPublicationError):
        collector().normalize(b"invalid JSON")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code", [(403, "sec_http_error"), (429, "sec_rate_limit"), (302, "sec_http_error")]
)
async def test_no_redirects_or_untrusted_error_body(status, code):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            status, text="Never persist secrets", headers={"Location": "https://evil.example"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        test = SECCompanyCollector("0000320193", "MarketAI fixture@example.org", client=client)
        with pytest.raises(CompanyPublicationError) as error:
            await test.collect()
        assert error.value.code == code
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_bounded_successful_transport():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload()))
    ) as client:
        test = SECCompanyCollector(
            "0000320193", "MarketAI fixture@example.org", now=NOW, client=client
        )
        assert len(await test.collect()) == 3
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 4_000_001))
    ) as client:
        test.client = client
        with pytest.raises(CompanyPublicationError, match="sec_response_too_large"):
            await test.collect()
