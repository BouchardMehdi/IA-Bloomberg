from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector, NormalizedArticle
from app.services.ingestion import ArticleIngestionService

SOURCE_ID = UUID("00000000-0000-0000-0000-000000000010")
RUN_ID = UUID("00000000-0000-0000-0000-000000000020")


def make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def make_collector() -> Mock:
    collector = Mock(spec=BaseCollector)
    collector.collect = AsyncMock()
    return collector


@pytest.mark.asyncio
async def test_successful_ingestion_completes_run_history() -> None:
    session = make_session()
    collector = make_collector()
    collector.collect.return_value = [
        NormalizedArticle(
            external_id="one",
            url="https://www.ecb.europa.eu/one",
            title="Example",
            content="Example content",
            language="en",
            published_at=datetime(2026, 9, 30, tzinfo=UTC),
            fetched_at=datetime(2026, 9, 30, tzinfo=UTC),
            content_hash="a" * 64,
        )
    ]
    service = ArticleIngestionService(session)
    service.repository.upsert_source = AsyncMock(return_value=SOURCE_ID)
    service.repository.insert_new = AsyncMock(return_value=1)
    service.run_repository.start = AsyncMock(return_value=RUN_ID)
    service.run_repository.succeed = AsyncMock()

    stats = await service.run(collector, trigger="scheduled")

    assert stats.run_id == RUN_ID
    assert stats.inserted == 1
    service.run_repository.succeed.assert_awaited_once()
    assert session.commit.await_count == 2
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_collection_is_recorded_before_error_is_raised() -> None:
    session = make_session()
    collector = make_collector()
    collector.collect.side_effect = RuntimeError("feed unavailable")
    service = ArticleIngestionService(session)
    service.repository.upsert_source = AsyncMock(return_value=SOURCE_ID)
    service.run_repository.start = AsyncMock(return_value=RUN_ID)
    service.run_repository.fail = AsyncMock()

    with pytest.raises(RuntimeError, match="feed unavailable"):
        await service.run(collector)

    service.run_repository.fail.assert_awaited_once()
    error_message = service.run_repository.fail.await_args.kwargs["error_message"]
    assert error_message == "RuntimeError: feed unavailable"
    session.rollback.assert_awaited_once()
    assert session.commit.await_count == 2
