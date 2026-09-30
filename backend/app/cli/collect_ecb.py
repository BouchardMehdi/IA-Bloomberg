import asyncio
import logging

from app.collectors.ecb import ECBPressCollector
from app.db.session import async_session_factory
from app.services.ingestion import ArticleIngestionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def collect() -> None:
    async with async_session_factory() as session:
        stats = await ArticleIngestionService(session).run(ECBPressCollector())
    logger.info(
        "ECB collection completed: fetched=%s inserted=%s duplicates=%s",
        stats.fetched,
        stats.inserted,
        stats.duplicates,
    )


if __name__ == "__main__":
    asyncio.run(collect())
