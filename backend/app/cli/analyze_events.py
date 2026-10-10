import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.semantic.client import configured_semantic_client
from app.services.semantic_analysis import SemanticAnalysisService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def analyze(limit: int, source: str | None = None) -> None:
    settings = get_settings()
    client = configured_semantic_client(settings)
    async with async_session_factory() as session:
        names = {
            "ecb": "European Central Bank",
            "fed": "Federal Reserve Board",
            "sec": "SEC EDGAR 8-K",
        }
        stats = await SemanticAnalysisService(
            session, client, require_document=settings.document_collection_enabled
        ).process_pending(limit, source_name=names.get(source))
    logger.info(
        "Semantic analysis completed: succeeded=%s failed=%s partial=%s facts_created=%s",
        stats.succeeded,
        stats.failed,
        stats.partial,
        stats.facts_created,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze pending events with Ollama")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--source", choices=["ecb", "fed", "sec"])
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    asyncio.run(analyze(args.limit, args.source))


if __name__ == "__main__":
    main()
