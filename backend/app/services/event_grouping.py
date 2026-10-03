import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.company import EventCompany
from app.models.event import Event, EventArticle
from app.repositories.events import ACCESSION_PATTERN


def document_identity(article: Article) -> str | None:
    if "www.sec.gov/Archives/edgar/data/" in article.url:
        match = ACCESSION_PATTERN.search(article.external_id or "")
        if match:
            return "sec:" + match.group("accession").replace("-", "")
        match = re.search(r"/Archives/edgar/data/\d+/(\d{18})/", article.url)
        if match:
            return "sec:" + match.group(1)
    # A shared RSS headline or short excerpt is never enough to merge facts.
    if article.full_content and not article.content_truncated and len(article.full_content) >= 500:
        if article.published_at is None:
            return None
        text = " ".join(article.full_content.split())
        digest = hashlib.sha256(text.encode()).hexdigest()
        return f"text:{article.source_id}:{article.published_at.date()}:{digest}"
    return None


@dataclass(frozen=True)
class GroupingStats:
    grouped: int


class EventGroupingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def process(self) -> GroupingStats:
        # Grouping runs in the single extraction loop, before semantic analysis.
        rows = (
            await self.session.execute(
                select(Event, Article)
                .join(EventArticle, EventArticle.event_id == Event.id)
                .join(Article, Article.id == EventArticle.article_id)
                .where(
                    Event.merged_into_event_id.is_(None), EventArticle.is_primary_source.is_(True)
                )
                .order_by(Event.created_at, Event.id)
                .with_for_update(of=Event)
            )
        ).all()
        canonical: dict[str, Event] = {}
        grouped = 0
        for event, article in rows:
            identity = document_identity(article)
            if identity is None:
                continue
            target = canonical.setdefault(identity, event)
            if target.id == event.id:
                continue
            links = (
                (
                    await self.session.execute(
                        select(EventArticle).where(EventArticle.event_id == event.id)
                    )
                )
                .scalars()
                .all()
            )
            for link in links:
                await self.session.execute(
                    insert(EventArticle)
                    .values(
                        event_id=target.id,
                        article_id=link.article_id,
                        is_primary_source=False,
                        relevance_score=1.0,
                    )
                    .on_conflict_do_nothing()
                )
            # Keep the original event and all its analysis history for auditability.
            event.merged_into_event_id = target.id
            event.status = "grouped"
            grouped += 1
        await self.session.flush()
        await self.session.execute(
            insert(EventCompany)
            .from_select(
                ["id", "event_id", "company_id", "role"],
                select(
                    func.gen_random_uuid(),
                    Event.merged_into_event_id,
                    EventCompany.company_id,
                    EventCompany.role,
                )
                .join(Event, Event.id == EventCompany.event_id)
                .where(Event.merged_into_event_id.is_not(None)),
            )
            .on_conflict_do_nothing()
        )
        await self.session.commit()
        return GroupingStats(grouped)
