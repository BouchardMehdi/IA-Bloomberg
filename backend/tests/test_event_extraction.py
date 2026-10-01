import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.event import Event
from app.models.source import Source
from app.repositories.events import EventRepository, PendingArticle, parse_sec_filing_title
from app.services.event_extraction import DeterministicEventExtractionService


def make_pending_article(source_type: str = "regulator") -> PendingArticle:
    source = Source(
        id=uuid.uuid4(),
        name="Test source",
        source_type=source_type,
        url="https://example.com",
        country="US",
        region="NORTH_AMERICA",
        reliability_score=1.0,
    )
    article = Article(
        id=uuid.uuid4(),
        source_id=source.id,
        url="https://example.com/filing",
        title="8-K - Example Corporation",
        content="Filed: 2026-09-30",
        language="en",
        published_at=datetime(2026, 9, 30, 20, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 9, 30, 20, 1, tzinfo=UTC),
        content_hash="a" * 64,
    )
    return PendingArticle(article=article, source=source)


@pytest.mark.asyncio
async def test_repository_creates_a_traceable_central_bank_event() -> None:
    session = AsyncMock(spec=AsyncSession)
    repository = EventRepository(session)
    pending = make_pending_article(source_type="central_bank")

    await repository.add_from_article(pending)

    event = session.add.call_args.args[0]
    assert isinstance(event, Event)
    assert event.deduplication_key == f"primary-article:{pending.article.id}"
    assert event.event_type == "central_bank_announcement"
    assert event.status == "enriched"
    assert event.extraction_version == "deterministic-v1"
    assert event.structured_data == {
        "announcement_kind": "official_publication",
        "institution": "Test source",
    }
    assert event.confidence_score == 1.0
    assert event.article_links[0].article is pending.article
    assert event.article_links[0].is_primary_source is True


@pytest.mark.asyncio
async def test_extraction_drains_all_pending_batches() -> None:
    session = AsyncMock(spec=AsyncSession)
    service = DeterministicEventExtractionService(session)
    pending = make_pending_article(source_type="central_bank")
    repository = Mock(spec=EventRepository)
    repository.lock_unenriched_events = AsyncMock(side_effect=[[], []])
    repository.lock_pending_articles = AsyncMock(side_effect=[[pending], []])
    repository.add_from_article = AsyncMock()
    repository.enrich_event = AsyncMock()
    service.repository = repository

    stats = await service.process_pending(batch_size=1)

    assert stats.created == 1
    assert stats.enriched == 0
    assert repository.lock_pending_articles.await_count == 2
    repository.add_from_article.assert_awaited_once_with(pending)
    assert session.commit.await_count == 3


def test_sec_company_and_cik_are_parsed_from_a_filing_title() -> None:
    result = parse_sec_filing_title("8-K/A - Example Holdings, Inc. (0001234567) (Filer)")

    assert result is not None
    assert result.form == "8-K/A"
    assert result.name == "Example Holdings, Inc."
    assert result.cik == "0001234567"


def test_non_sec_title_is_not_treated_as_a_company_filing() -> None:
    assert parse_sec_filing_title("Federal Reserve issues FOMC statement") is None
