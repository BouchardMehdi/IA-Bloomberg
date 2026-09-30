from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine


class HealthService:
    async def check_dependencies(self) -> dict[str, bool]:
        return {
            "postgres": await self._check_postgres(),
            "redis": await self._check_redis(),
        }

    async def _check_postgres(self) -> bool:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def _check_redis(self) -> bool:
        client = Redis.from_url(get_settings().redis_url)
        try:
            return bool(await client.ping())
        except Exception:
            return False
        finally:
            await client.aclose()


def get_health_service() -> HealthService:
    return HealthService()
