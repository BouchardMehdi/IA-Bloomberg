import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection_run import CollectionRun
from app.models.source import Source


@dataclass(frozen=True)
class CollectionRunRecord:
    run: CollectionRun
    source_name: str


class CollectionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(
        self,
        source_id: uuid.UUID,
        trigger: str,
        started_at: datetime,
    ) -> uuid.UUID:
        run = CollectionRun(
            source_id=source_id,
            trigger=trigger,
            status="running",
            started_at=started_at,
        )
        self.session.add(run)
        await self.session.flush()
        return run.id

    async def succeed(
        self,
        run_id: uuid.UUID,
        *,
        finished_at: datetime,
        duration_ms: int,
        fetched: int,
        inserted: int,
        duplicates: int,
    ) -> None:
        await self.session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == run_id)
            .values(
                status="success",
                finished_at=finished_at,
                duration_ms=duration_ms,
                fetched_count=fetched,
                inserted_count=inserted,
                duplicate_count=duplicates,
                error_message=None,
            )
        )

    async def fail(
        self,
        run_id: uuid.UUID,
        *,
        finished_at: datetime,
        duration_ms: int,
        error_message: str,
    ) -> None:
        await self.session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == run_id)
            .values(
                status="failed",
                finished_at=finished_at,
                duration_ms=duration_ms,
                error_message=error_message[:2000],
            )
        )

    async def list_latest(self, limit: int, offset: int) -> tuple[list[CollectionRunRecord], int]:
        statement = (
            select(CollectionRun, Source.name)
            .join(Source, Source.id == CollectionRun.source_id)
            .order_by(CollectionRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(statement)).all()
        total = (await self.session.execute(select(func.count(CollectionRun.id)))).scalar_one()
        return [CollectionRunRecord(run=row[0], source_name=row[1]) for row in rows], total
