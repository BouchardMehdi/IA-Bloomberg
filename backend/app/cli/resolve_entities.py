import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.services.entity_resolution import EntityResolutionService


async def run(sync: bool, limit: int) -> None:
    async with async_session_factory() as session:
        service = EntityResolutionService(session)
        if sync:
            await service.sync_registry(get_settings().sec_user_agent, force=True)
        count = await service.process_pending(limit)
        logging.info("Entity resolution completed: processed=%s", count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve identities without LLM calls")
    parser.add_argument("--sync", action="store_true", help="Refresh the official SEC registry")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 5000:
        parser.error("--limit must be between 1 and 5000")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.sync, args.limit))


if __name__ == "__main__":
    main()
