import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.documents import OfficialDocumentClient, UnsupportedDocument
from app.models.article import Article
from app.models.source import Source

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentStats:
    succeeded: int = 0
    failed: int = 0
    unsupported: int = 0


class DocumentContentService:
    def __init__(self, session: AsyncSession, client: OfficialDocumentClient) -> None:
        self.session = session
        self.client = client

    async def process_pending(self, limit: int = 5, source_name: str | None = None) -> ContentStats:
        counts = {"succeeded": 0, "failed": 0, "unsupported": 0}
        for _ in range(limit):
            now = datetime.now(UTC)
            statement = (
                select(Article)
                .where(
                    or_(
                        and_(Article.content_status == "pending", Article.content_attempts < 3),
                        and_(
                            Article.content_status == "failed",
                            Article.content_attempts < 3,
                            Article.content_next_retry_at <= now,
                        ),
                        and_(
                            Article.content_status == "fetching",
                            Article.content_next_retry_at <= now,
                        ),
                    ),
                )
                .order_by(Article.published_at.desc().nulls_last(), Article.id)
                .limit(1)
                .with_for_update(of=Article, skip_locked=True)
            )
            if source_name is not None:
                statement = statement.join(Source, Source.id == Article.source_id).where(
                    Source.name == source_name
                )
            article = (await self.session.execute(statement)).scalar_one_or_none()
            if article is None:
                await self.session.rollback()
                break
            if article.content_attempts >= 3:
                article.content_status = "failed"
                article.content_error = "Retrieval interrupted after final attempt"
                article.content_next_retry_at = None
                await self.session.commit()
                counts["failed"] += 1
                continue
            article.content_attempts += 1
            article.content_status = "fetching"
            article.content_next_retry_at = now + timedelta(minutes=10)
            await self.session.commit()
            try:
                result = await self.client.fetch(article.url)
                article.full_content = result.text
                article.full_content_hash = result.content_hash
                article.document_url = result.url
                article.content_truncated = result.truncated
                article.content_fetched_at = datetime.now(UTC)
                article.content_error = None
                article.content_status = "success"
                article.content_next_retry_at = None
                counts["succeeded"] += 1
            except UnsupportedDocument as error:
                article.content_status = "unsupported"
                article.content_error = str(error)[:2000]
                article.content_next_retry_at = None
                counts["unsupported"] += 1
            except Exception as error:
                article.content_status = "failed"
                article.content_error = f"{type(error).__name__}: {error}"[:2000]
                article.content_next_retry_at = (
                    datetime.now(UTC) + timedelta(minutes=5 * 2 ** (article.content_attempts - 1))
                    if article.content_attempts < 3
                    else None
                )
                counts["failed"] += 1
                logger.warning(
                    "Document fetch failed: article=%s error=%s", article.id, type(error).__name__
                )
            await self.session.commit()
        return ContentStats(**counts)
