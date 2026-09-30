from datetime import UTC, datetime
from pathlib import Path

from app.collectors.fed import FedPressCollector

FIXTURE = Path(__file__).parent / "fixtures" / "fed_press.xml"


def test_fed_feed_is_normalized_without_network() -> None:
    articles = FedPressCollector().normalize(FIXTURE.read_bytes())

    assert len(articles) == 2
    first = articles[0]
    assert first.external_id == (
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
    )
    assert first.title == "Federal Reserve issues FOMC statement"
    assert first.url == (
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm"
    )
    assert first.content == (
        "The Federal Open Market Committee decided to maintain the target range."
    )
    assert first.language == "en"
    assert first.published_at == datetime(2026, 9, 16, 18, 0, tzinfo=UTC)
    assert len(first.content_hash) == 64


def test_fed_relative_links_are_made_absolute() -> None:
    articles = FedPressCollector().normalize(FIXTURE.read_bytes())

    assert articles[1].external_id == "fed-example-2"
    assert articles[1].url == (
        "https://www.federalreserve.gov/newsevents/pressreleases/orders20260915a.htm"
    )
    assert articles[1].content == "The Board approved the application."


def test_fed_collector_describes_an_official_primary_source() -> None:
    collector = FedPressCollector()

    assert collector.source_type == "central_bank"
    assert collector.country == "US"
    assert collector.reliability_score == 1.0
