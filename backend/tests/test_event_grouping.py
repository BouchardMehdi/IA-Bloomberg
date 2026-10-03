import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.article import Article
from app.models.event import Event, EventArticle
from app.services.event_grouping import EventGroupingService, document_identity


def test_same_sec_filing_matches_index_and_report_urls() -> None:
    index = Article(
        url="https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/filing-index.htm",
        external_id="urn:tag:sec.gov,2008:accession-number=0001234567-26-000001",
    )
    report = Article(url=index.url.replace("filing-index.htm", "report.htm"))
    assert document_identity(index) == document_identity(report)
    amendment = Article(url=report.url.replace("000123456726000001", "000123456726000002"))
    assert document_identity(index) != document_identity(amendment)


def test_identical_headlines_and_rss_excerpts_do_not_merge_events() -> None:
    article = Article(
        url="https://www.ecb.europa.eu/press/test",
        title="Policy decisions",
        content="Rates unchanged",
    )
    assert document_identity(article) is None


@pytest.mark.asyncio
async def test_grouping_keeps_original_events_and_adds_source_links() -> None:
    original = Event(id=uuid.uuid4(), status="analyzed")
    duplicate = Event(id=uuid.uuid4(), status="enriched")
    article = Article(
        id=uuid.uuid4(),
        url="https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/report.htm",
    )
    first = Mock()
    first.all.return_value = [(original, article), (duplicate, article)]
    links = Mock()
    links.scalars.return_value.all.return_value = [EventArticle(article_id=article.id)]
    session = AsyncMock()
    session.execute.side_effect = [first, links, Mock(), Mock()]
    stats = await EventGroupingService(session).process()
    assert stats.grouped == 1
    assert duplicate.merged_into_event_id == original.id
    assert duplicate.status == "grouped"
    assert original.status == "analyzed"
    session.delete.assert_not_awaited()
    session.commit.assert_awaited_once()


def test_identical_full_text_requires_same_source_date_and_no_truncation() -> None:
    article = Article(
        url="https://www.ecb.europa.eu/press/test",
        source_id=uuid.uuid4(),
        published_at=datetime(2026, 10, 3, tzinfo=UTC),
        full_content="Official publication. " * 30,
        content_truncated=False,
    )
    identity = document_identity(article)
    assert identity is not None
    article.published_at = datetime(2026, 10, 4, tzinfo=UTC)
    assert identity != document_identity(article)
    article.content_truncated = True
    assert document_identity(article) is None
