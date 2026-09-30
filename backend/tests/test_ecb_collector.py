from datetime import UTC, datetime
from pathlib import Path

from app.collectors.ecb import ECBPressCollector

FIXTURE = Path(__file__).parent / "fixtures" / "ecb_press.xml"


def test_ecb_feed_is_normalized_without_network() -> None:
    articles = ECBPressCollector().normalize(FIXTURE.read_bytes())

    assert len(articles) == 2
    first = articles[0]
    assert first.external_id == "ecb-example-1"
    assert first.title == "Monetary policy decisions"
    assert first.url == (
        "https://www.ecb.europa.eu/press/pr/date/2026/html/example.en.html?ref=press"
    )
    assert first.content == "The Governing Council decided to keep rates unchanged."
    assert first.language == "en"
    assert first.published_at == datetime(2026, 9, 24, 12, 15, tzinfo=UTC)
    assert len(first.content_hash) == 64


def test_relative_links_are_made_absolute() -> None:
    articles = ECBPressCollector().normalize(FIXTURE.read_bytes())

    assert articles[1].url == (
        "https://www.ecb.europa.eu/press/financial-stability-publications/fsr/html/example.en.html"
    )
    assert articles[1].content == "Risks remain contained & banks are resilient."


def test_normalization_produces_a_stable_hash() -> None:
    collector = ECBPressCollector()

    first_run = collector.normalize(FIXTURE.read_bytes())
    second_run = collector.normalize(FIXTURE.read_bytes())

    assert [article.content_hash for article in first_run] == [
        article.content_hash for article in second_run
    ]


def test_items_without_content_use_the_url_in_their_hash() -> None:
    payload = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Same speech title</title><link>https://www.ecb.europa.eu/one</link></item>
      <item><title>Same speech title</title><link>https://www.ecb.europa.eu/two</link></item>
    </channel></rss>"""

    articles = ECBPressCollector().normalize(payload)

    assert len(articles) == 2
    assert articles[0].content_hash != articles[1].content_hash
