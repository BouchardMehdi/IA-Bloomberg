from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.repositories.articles import ArticleRepository


@dataclass(frozen=True)
class IngestionStats:
    fetched: int
    inserted: int
    duplicates: int


class ArticleIngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ArticleRepository(session)

    async def run(self, collector: BaseCollector) -> IngestionStats:
        articles = await collector.collect()
        try:
            source_id = await self.repository.upsert_source(collector)
            inserted = await self.repository.insert_new(source_id, articles)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return IngestionStats(
            fetched=len(articles),
            inserted=inserted,
            duplicates=len(articles) - inserted,
        )
