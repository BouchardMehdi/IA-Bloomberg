from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.events import EventRepository


@dataclass(frozen=True)
class ExtractionStats:
    created: int
    enriched: int


class DeterministicEventExtractionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = EventRepository(session)

    async def process_pending(self, batch_size: int = 100) -> ExtractionStats:
        enriched = 0
        while True:
            pending_events = await self.repository.lock_unenriched_events(batch_size)
            for pending in pending_events:
                await self.repository.enrich_event(pending)
            await self.session.commit()
            enriched += len(pending_events)
            if len(pending_events) < batch_size:
                break

        created = 0
        while True:
            pending_articles = await self.repository.lock_pending_articles(batch_size)
            for pending in pending_articles:
                await self.repository.add_from_article(pending)
            await self.session.commit()
            created += len(pending_articles)
            if len(pending_articles) < batch_size:
                return ExtractionStats(created=created, enriched=enriched)
