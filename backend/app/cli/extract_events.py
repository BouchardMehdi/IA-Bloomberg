import asyncio
import logging

from app.db.session import async_session_factory
from app.services.event_extraction import DeterministicEventExtractionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def extract() -> None:
    async with async_session_factory() as session:
        extracted = await DeterministicEventExtractionService(session).process_pending()
    logger.info("Deterministic event extraction completed: extracted=%s", extracted)


if __name__ == "__main__":
    asyncio.run(extract())
