from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.articles import ArticleRepository
from app.schemas.article import ArticlePage, ArticleRead


class ArticleService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ArticleRepository(session)

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
            )
            for record in records
        ]
        return ArticlePage(items=items, total=total, limit=limit, offset=offset)
