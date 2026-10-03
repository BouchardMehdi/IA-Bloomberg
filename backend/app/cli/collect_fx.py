import asyncio
import logging

from app.db.session import async_session_factory
from app.market.ecb_fx import EcbFxClient
from app.services.fx_collection import FxCollectionService


async def main():
    async with async_session_factory() as session:
        result = await FxCollectionService(session).collect(EcbFxClient())
        logging.info("ECB FX collection completed: %s", result)
        if result["status"] == "failed":
            raise SystemExit("Collecte des taux échouée ; les données précédentes sont conservées.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
