import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.semantic.ollama import OllamaSemanticClient
from app.services.semantic_analysis import SemanticAnalysisService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def analyze(limit: int) -> None:
    settings = get_settings()
    client = OllamaSemanticClient(settings.ollama_base_url, settings.ollama_model)
    async with async_session_factory() as session:
        stats = await SemanticAnalysisService(session, client).process_pending(limit)
    logger.info(
        "Semantic analysis completed: succeeded=%s failed=%s",
        stats.succeeded,
        stats.failed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze pending events with Ollama")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    asyncio.run(analyze(args.limit))


if __name__ == "__main__":
    main()
