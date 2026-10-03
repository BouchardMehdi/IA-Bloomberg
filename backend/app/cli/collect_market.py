import asyncio
import logging

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.market.provider_registry import configured_price_providers
from app.services.market_data import MarketDataService


async def main():
    providers = configured_price_providers(get_settings())
    if not providers:
        raise SystemExit("Ajouter ALPHA_VANTAGE_API_KEY dans .env pour activer les cours.")
    for provider in providers:
        async with async_session_factory() as session:
            stats = await MarketDataService(session).collect(provider)
            logging.info("Market collection completed: %s", stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
