from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.event import Event, EventArticle
from app.models.source import Source


@dataclass(frozen=True)
class PendingArticle:
    article: Article
    source: Source


@dataclass(frozen=True)
class EventRecord:
    event: Event
    source_name: str
    article_url: str


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_pending_articles(self, limit: int) -> list[PendingArticle]:
        statement = (
            select(Article, Source)
            .join(Source, Source.id == Article.source_id)
            .outerjoin(EventArticle, EventArticle.article_id == Article.id)
            .where(EventArticle.id.is_(None))
            .order_by(func.coalesce(Article.published_at, Article.fetched_at), Article.id)
            .limit(limit)
            .with_for_update(of=Article, skip_locked=True)
        )
        rows = (await self.session.execute(statement)).all()
        return [PendingArticle(article=row[0], source=row[1]) for row in rows]

    def add_from_article(self, pending: PendingArticle) -> None:
        article = pending.article
        source = pending.source
        event_type = (
            "regulatory_filing"
            if source.source_type == "regulator"
            else "central_bank_announcement"
        )
        event = Event(
            deduplication_key=f"primary-article:{article.id}",
            event_type=event_type,
            title=article.title,
            description=article.content,
            event_datetime=article.published_at or article.fetched_at,
            event_time_type="published",
            status="detected",
            confidence_score=1.0,
            country=source.country,
            region=source.region,
        )
        event.article_links.append(
            EventArticle(
                article=article,
                is_primary_source=True,
                relevance_score=1.0,
            )
        )
        self.session.add(event)

    async def list_latest(self, limit: int, offset: int) -> tuple[list[EventRecord], int]:
        statement = (
            select(Event, Source.name, Article.url)
            .join(EventArticle, EventArticle.event_id == Event.id)
            .join(Article, Article.id == EventArticle.article_id)
            .join(Source, Source.id == Article.source_id)
            .where(EventArticle.is_primary_source.is_(True))
            .order_by(Event.event_datetime.desc(), Event.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(statement)).all()
        total = (await self.session.execute(select(func.count(Event.id)))).scalar_one()
        return [
            EventRecord(event=row[0], source_name=row[1], article_url=row[2]) for row in rows
        ], total
