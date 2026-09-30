from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.collection_runs import CollectionRunRepository
from app.schemas.collection_run import CollectionRunPage, CollectionRunRead


class CollectionRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = CollectionRunRepository(session)

    async def list_latest(self, limit: int, offset: int) -> CollectionRunPage:
        records, total = await self.repository.list_latest(limit=limit, offset=offset)
        items = [
            CollectionRunRead(
                id=record.run.id,
                source_name=record.source_name,
                trigger=record.run.trigger,
                status=record.run.status,
                started_at=record.run.started_at,
                finished_at=record.run.finished_at,
                duration_ms=record.run.duration_ms,
                fetched_count=record.run.fetched_count,
                inserted_count=record.run.inserted_count,
                duplicate_count=record.run.duplicate_count,
                error_message=record.run.error_message,
            )
            for record in records
        ]
        return CollectionRunPage(items=items, total=total, limit=limit, offset=offset)
