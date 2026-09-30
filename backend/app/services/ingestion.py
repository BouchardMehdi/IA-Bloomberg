import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import BaseCollector
from app.repositories.articles import ArticleRepository
from app.repositories.collection_runs import CollectionRunRepository


@dataclass(frozen=True)
class IngestionStats:
    run_id: uuid.UUID
    fetched: int
    inserted: int
    duplicates: int
    duration_ms: int


class ArticleIngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ArticleRepository(session)
        self.run_repository = CollectionRunRepository(session)

    async def run(
        self,
        collector: BaseCollector,
        trigger: Literal["manual", "scheduled"] = "manual",
    ) -> IngestionStats:
        started_at = datetime.now(UTC)
        started_clock = time.perf_counter()
        try:
            source_id = await self.repository.upsert_source(collector)
            run_id = await self.run_repository.start(source_id, trigger, started_at)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        try:
            articles = await collector.collect()
            inserted = await self.repository.insert_new(source_id, articles)
            duration_ms = round((time.perf_counter() - started_clock) * 1000)
            duplicates = len(articles) - inserted
            await self.run_repository.succeed(
                run_id,
                finished_at=datetime.now(UTC),
                duration_ms=duration_ms,
                fetched=len(articles),
                inserted=inserted,
                duplicates=duplicates,
            )
            await self.session.commit()
        except Exception as error:
            await self.session.rollback()
            duration_ms = round((time.perf_counter() - started_clock) * 1000)
            await self.run_repository.fail(
                run_id,
                finished_at=datetime.now(UTC),
                duration_ms=duration_ms,
                error_message=f"{type(error).__name__}: {error}",
            )
            await self.session.commit()
            raise

        return IngestionStats(
            run_id=run_id,
            fetched=len(articles),
            inserted=inserted,
            duplicates=duplicates,
            duration_ms=duration_ms,
        )
