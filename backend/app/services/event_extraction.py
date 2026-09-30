from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.events import EventRepository


class DeterministicEventExtractionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = EventRepository(session)

    async def process_pending(self, batch_size: int = 100) -> int:
        total = 0
        while True:
            pending_articles = await self.repository.lock_pending_articles(batch_size)
            for pending in pending_articles:
                self.repository.add_from_article(pending)
            await self.session.commit()
            total += len(pending_articles)
            if len(pending_articles) < batch_size:
                return total
