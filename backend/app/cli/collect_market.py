import asyncio
import logging

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.market.alpha_vantage import AlphaVantageClient
from app.services.market_data import MarketDataService


async def main():
    key = get_settings().alpha_vantage_api_key.get_secret_value()
    if not key:
        raise SystemExit("Ajouter ALPHA_VANTAGE_API_KEY dans .env pour activer les cours.")
    async with async_session_factory() as session:
        stats = await MarketDataService(session).collect(AlphaVantageClient(key))
        logging.info("Market collection completed: %s", stats)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
