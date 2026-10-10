import asyncio

from app.db.session import async_session_factory
from app.services.wls_automation import WlsAutomationService


async def main():
    async with async_session_factory() as session:
        print(await WlsAutomationService(session).collect())


if __name__ == "__main__":
    asyncio.run(main())
