from datetime import UTC, datetime
from pathlib import Path

from app.collectors.sec import SEC8KCollector

FIXTURE = Path(__file__).parent / "fixtures" / "sec_8k.xml"
USER_AGENT = "MarketAI Tests tests@example.com"


def test_sec_atom_feed_is_normalized_without_network() -> None:
    articles = SEC8KCollector(USER_AGENT).normalize(FIXTURE.read_bytes())

    assert len(articles) == 2
    first = articles[0]
    assert first.external_id == "urn:tag:sec.gov,2008:accession-number=0001234567-26-000001"
    assert first.title == "8-K - Example Corporation (0001234567) (Filer)"
    assert first.url == (
        "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/example-20260930.htm"
    )
    assert first.content == "Filed: 2026-09-30 AccNo: 0001234567-26-000001"
    assert first.language == "en"
    assert first.published_at == datetime(2026, 9, 30, 20, 28, 14, tzinfo=UTC)
    assert len(first.content_hash) == 64


def test_sec_relative_links_are_made_absolute() -> None:
    articles = SEC8KCollector(USER_AGENT).normalize(FIXTURE.read_bytes())

    assert articles[1].url == (
        "https://www.sec.gov/Archives/edgar/data/7654321/000765432126000002/amendment.htm"
    )


def test_sec_collector_uses_the_declared_user_agent() -> None:
    collector = SEC8KCollector(USER_AGENT)

    assert collector.user_agent == USER_AGENT
    assert collector.source_type == "regulator"
    assert collector.reliability_score == 1.0
