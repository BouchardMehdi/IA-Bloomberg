from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.events import EventRepository
from app.schemas.event import EventPage, EventRead


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = EventRepository(session)

    async def list_latest(self, limit: int, offset: int) -> EventPage:
        records, total = await self.repository.list_latest(limit=limit, offset=offset)
        return EventPage(
            items=[
                EventRead(
                    id=record.event.id,
                    event_type=record.event.event_type,
                    title=record.event.title,
                    description=record.event.description,
                    event_datetime=record.event.event_datetime,
                    status=record.event.status,
                    confidence_score=record.event.confidence_score,
                    country=record.event.country,
                    region=record.event.region,
                    source_name=record.source_name,
                    article_url=record.article_url,
                )
                for record in records
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
