import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector, NormalizedArticle
from app.models.article import Article
from app.models.source import Source


@dataclass(frozen=True)
class ArticleRecord:
    article: Article
    source_name: str


class ArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_source(self, collector: BaseCollector) -> uuid.UUID:
        statement = (
            insert(Source)
            .values(
                name=collector.source_name,
                source_type=collector.source_type,
                url=collector.source_url,
                country=collector.country,
                region=collector.region,
                reliability_score=collector.reliability_score,
                enabled=True,
            )
            .on_conflict_do_update(
                index_elements=[Source.name],
                set_={
                    "source_type": collector.source_type,
                    "url": collector.source_url,
                    "country": collector.country,
                    "region": collector.region,
                    "reliability_score": collector.reliability_score,
                    "enabled": True,
                    "updated_at": func.now(),
                },
            )
            .returning(Source.id)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def insert_new(self, source_id: uuid.UUID, articles: list[NormalizedArticle]) -> int:
        inserted = 0
        for article in articles:
            statement = (
                insert(Article)
                .values(source_id=source_id, **article.model_dump())
                .on_conflict_do_nothing()
            )
            result = await self.session.execute(statement)
            inserted += result.rowcount or 0
        return inserted

    async def list_latest(self, limit: int, offset: int) -> tuple[list[ArticleRecord], int]:
        ordering_date = func.coalesce(Article.published_at, Article.fetched_at)
        statement = (
            select(Article, Source.name)
            .join(Source, Source.id == Article.source_id)
            .order_by(ordering_date.desc(), Article.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(statement)).all()
        total = (await self.session.execute(select(func.count(Article.id)))).scalar_one()
        return [ArticleRecord(article=row[0], source_name=row[1]) for row in rows], total
