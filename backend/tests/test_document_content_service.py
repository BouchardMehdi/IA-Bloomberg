from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.collectors.documents import DocumentContent, UnsupportedDocument
from app.models.article import Article
from app.services.document_content import DocumentContentService


def setup_service(attempts: int = 0):
    article = Article(
        url="https://www.ecb.europa.eu/press/test",
        content="RSS excerpt",
        content_status="pending",
        content_attempts=attempts,
    )
    first = Mock()
    first.scalar_one_or_none.return_value = article
    empty = Mock()
    empty.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute.side_effect = [first, empty]
    client = Mock()
    client.fetch = AsyncMock()
    return DocumentContentService(session, client), article


@pytest.mark.asyncio
async def test_success_preserves_rss_and_saves_document_provenance() -> None:
    service, article = setup_service()
    service.client.fetch.return_value = DocumentContent(
        "Complete text", article.url, "a" * 64, False
    )
    stats = await service.process_pending(2)
    assert stats.succeeded == 1
    assert article.content == "RSS excerpt"
    assert article.full_content == "Complete text"
    assert article.document_url == article.url
    assert article.content_status == "success"
    assert article.content_next_retry_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts,retry", [(0, True), (2, False)])
async def test_failed_retrieval_schedules_only_bounded_retries(attempts: int, retry: bool) -> None:
    service, article = setup_service(attempts)
    service.client.fetch.side_effect = TimeoutError("timeout")
    stats = await service.process_pending(1)
    assert stats.failed == 1
    assert article.content_status == "failed"
    assert article.content_attempts == attempts + 1
    assert (article.content_next_retry_at is not None) == retry
    if retry:
        assert article.content_next_retry_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_unsupported_document_does_not_retry() -> None:
    service, article = setup_service()
    service.client.fetch.side_effect = UnsupportedDocument("PDF")
    stats = await service.process_pending(1)
    assert stats.unsupported == 1
    assert article.content_status == "unsupported"
    assert article.content_next_retry_at is None


@pytest.mark.asyncio
async def test_interrupted_final_attempt_releases_the_article() -> None:
    service, article = setup_service(3)
    article.content_status = "fetching"
    stats = await service.process_pending(1)
    assert stats.failed == 1
    assert article.content_status == "failed"
    service.client.fetch.assert_not_awaited()
