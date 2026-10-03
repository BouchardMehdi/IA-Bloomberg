from pathlib import Path

import httpx
import pytest

from app.collectors.documents import (
    OfficialDocumentClient,
    UnsupportedDocument,
    extract_document_html,
    sec_primary_document,
    validate_document_url,
)

FIXTURES = Path(__file__).parent / "fixtures"
SEC_INDEX = "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/filing-index.htm"


@pytest.mark.parametrize(
    "fixture,url",
    [
        ("ecb_document.html", "https://www.ecb.europa.eu/press/pr/date/2026/html/test.en.html"),
        ("fed_document.html", "https://www.federalreserve.gov/newsevents/pressreleases/test.htm"),
        ("sec_document.html", SEC_INDEX.replace("filing-index.htm", "report.htm")),
    ],
)
def test_extracts_publication_without_navigation_or_hidden_text(fixture: str, url: str) -> None:
    result = extract_document_html((FIXTURES / fixture).read_text(), url, 60000)
    assert len(result.text) >= 100
    assert not result.truncated
    assert "navigation" not in result.text.lower()
    assert "Hidden financial metadata" not in result.text
    assert "Footer text" not in result.text


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sec.gov/Archives/edgar/data/1/test.htm",
        "https://www.sec.gov.evil.test/Archives/edgar/data/1/test.htm",
        "https://127.0.0.1/press/test",
        "https://www.sec.gov:8443/Archives/edgar/data/1/test.htm",
        "https://www.ecb.europa.eu/press/../../secret",
        "https://www.sec.gov/private/test",
    ],
)
def test_rejects_unsupported_urls(url: str) -> None:
    with pytest.raises(UnsupportedDocument):
        validate_document_url(url)


def test_sec_index_selects_primary_report_instead_of_exhibit() -> None:
    url = sec_primary_document((FIXTURES / "sec_document_index.html").read_text(), SEC_INDEX)
    assert url == SEC_INDEX.replace("filing-index.htm", "report.htm")


def test_ecb_double_slash_path_is_normalized_without_changing_domain() -> None:
    assert (
        validate_document_url("https://www.ecb.europa.eu//press/test.en.html")
        == "https://www.ecb.europa.eu/press/test.en.html"
    )


@pytest.mark.asyncio
async def test_follows_sec_index_and_preserves_document_provenance() -> None:
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.headers["User-Agent"] == "MarketAI test@example.com"
        name = (
            "sec_document_index.html" if "-index.htm" in request.url.path else "sec_document.html"
        )
        return httpx.Response(
            200, text=(FIXTURES / name).read_text(), headers={"Content-Type": "text/html"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OfficialDocumentClient("MarketAI test@example.com", client=client).fetch(
            SEC_INDEX
        )
    assert len(requested) == 2
    assert result.url.endswith("report.htm")
    assert "USD 20 million" in result.text


@pytest.mark.asyncio
async def test_does_not_follow_redirect_to_an_external_domain() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://example.com/secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsupportedDocument):
            await OfficialDocumentClient("MarketAI test@example.com", client=client).fetch(
                SEC_INDEX
            )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_download_size_limit_and_unsupported_pdf() -> None:
    for headers, content in [
        ({"Content-Type": "text/html"}, b"a" * 101),
        ({"Content-Type": "application/pdf"}, b"pdf"),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request, body=content, metadata=headers: httpx.Response(
                    200, content=body, headers=metadata
                )
            )
        ) as client:
            with pytest.raises(UnsupportedDocument):
                await OfficialDocumentClient(
                    "MarketAI test@example.com", max_bytes=100, client=client
                ).fetch(SEC_INDEX)


def test_truncated_text_is_explicit_and_hashes_the_stored_text() -> None:
    result = extract_document_html(
        (FIXTURES / "ecb_document.html").read_text(), "https://www.ecb.europa.eu/press/test", 100
    )
    assert len(result.text) == 100
    assert result.truncated
