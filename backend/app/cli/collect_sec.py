import asyncio
import logging

from app.collectors.sec import SEC8KCollector
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.ingestion import ArticleIngestionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def collect() -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        stats = await ArticleIngestionService(session).run(SEC8KCollector(settings.sec_user_agent))
    logger.info(
        "SEC 8-K collection completed: run_id=%s fetched=%s inserted=%s "
        "duplicates=%s duration_ms=%s",
        stats.run_id,
        stats.fetched,
        stats.inserted,
        stats.duplicates,
        stats.duration_ms,
    )


if __name__ == "__main__":
    asyncio.run(collect())
