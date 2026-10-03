import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.articles import ArticleRepository
from app.schemas.article import ArticleDetail, ArticlePage, ArticleRead


class ArticleService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ArticleRepository(session)

    async def get(self, article_id: uuid.UUID) -> ArticleDetail | None:
        record = await self.repository.get(article_id)
        if record is None:
            return None
        article = record.article
        return ArticleDetail(
            **{
                name: getattr(article, name)
                for name in ArticleRead.model_fields
                if name != "source_name"
            },
            source_name=record.source_name,
            full_content=article.full_content,
        )

    async def list_latest(self, limit: int, offset: int) -> ArticlePage:
        records, total = await self.repository.list_latest(limit=limit, offset=offset)
        items = [
            ArticleRead(
                id=record.article.id,
                source_name=record.source_name,
                url=record.article.url,
                title=record.article.title,
                content=record.article.content,
                language=record.article.language,
                published_at=record.article.published_at,
                fetched_at=record.article.fetched_at,
                document_url=record.article.document_url,
                content_status=record.article.content_status,
                content_attempts=record.article.content_attempts,
                content_fetched_at=record.article.content_fetched_at,
                content_truncated=record.article.content_truncated,
                content_error=record.article.content_error,
            )
            for record in records
        ]
        return ArticlePage(items=items, total=total, limit=limit, offset=offset)
