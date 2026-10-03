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
    fed_collection_interval_minutes: int = Field(default=15, ge=1, le=1440)
    sec_collection_interval_minutes: int = Field(default=15, ge=1, le=1440)
    sec_user_agent: str = Field(
        default="MarketAI/0.1 contact@example.com",
        min_length=10,
        max_length=255,
    )
    event_extraction_interval_minutes: int = Field(default=1, ge=1, le=1440)
    ai_analysis_enabled: bool = False
    ai_analysis_interval_minutes: int = Field(default=5, ge=1, le=1440)
    ai_analysis_batch_size: int = Field(default=3, ge=1, le=50)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b-instruct"
    scheduler_run_on_start: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
