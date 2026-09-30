from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Market AI API"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://market_ai:change-me@localhost:5432/market_ai"
    redis_url: str = "redis://localhost:6379/0"
    backend_cors_origins: str = "http://localhost:3000,http://localhost"
    ecb_collection_interval_minutes: int = Field(default=15, ge=1, le=1440)
    scheduler_run_on_start: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
