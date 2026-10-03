import argparse
import asyncio
import logging

from app.collectors.documents import OfficialDocumentClient
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.document_content import DocumentContentService
from app.services.event_grouping import EventGroupingService


async def fetch(limit: int, source: str | None = None) -> None:
    settings = get_settings()
    client = OfficialDocumentClient(
        settings.sec_user_agent, settings.document_max_bytes, settings.document_max_chars
    )
    async with async_session_factory() as session:
        names = {
            "ecb": "European Central Bank",
            "fed": "Federal Reserve Board",
            "sec": "SEC EDGAR 8-K",
        }
        stats = await DocumentContentService(session, client).process_pending(
            limit, names.get(source)
        )
        grouping = await EventGroupingService(session).process()
    logging.info("Document retrieval: %s; grouping: %s", stats, grouping)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Fetch official publication text")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--source", choices=["ecb", "fed", "sec"])
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    asyncio.run(fetch(args.limit, args.source))


if __name__ == "__main__":
    main()
