import asyncio
import logging
import time

from app.collectors.ecb import ECBPressCollector
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.ingestion import ArticleIngestionService

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


def seconds_until_next_run(interval_minutes: int, elapsed_seconds: float) -> float:
    return max(1.0, interval_minutes * 60 - elapsed_seconds)


async def collect_ecb_once() -> None:
    async with async_session_factory() as session:
        stats = await ArticleIngestionService(session).run(
            ECBPressCollector(),
            trigger="scheduled",
        )
    logger.info(
        "Scheduled ECB collection completed: run_id=%s fetched=%s inserted=%s "
        "duplicates=%s duration_ms=%s",
        stats.run_id,
        stats.fetched,
        stats.inserted,
        stats.duplicates,
        stats.duration_ms,
    )


async def serve() -> None:
    settings = get_settings()
    interval = settings.ecb_collection_interval_minutes
    logger.info("ECB scheduler started: interval_minutes=%s", interval)

    if not settings.scheduler_run_on_start:
        await asyncio.sleep(interval * 60)

    while True:
        cycle_started = time.monotonic()
        try:
            await collect_ecb_once()
        except Exception:
            logger.exception("Scheduled ECB collection failed")

        delay = seconds_until_next_run(interval, time.monotonic() - cycle_started)
        logger.info("Next ECB collection in %.1f seconds", delay)
        await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(serve())
