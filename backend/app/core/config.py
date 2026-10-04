from functools import lru_cache

from pydantic import Field, SecretStr
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
    entity_registry_enabled: bool = True
    alpha_vantage_api_key: SecretStr = SecretStr("")
    market_daily_request_budget: int = Field(default=20, ge=1, le=25)
    earnings_calendar_enabled: bool = True
    company_publications_enabled: bool = True
    market_max_price_age_days: int = Field(default=7, ge=1, le=30)
    market_max_fx_age_days: int = Field(default=7, ge=1, le=30)
    fx_collection_enabled: bool = True
    fx_collection_interval_minutes: int = Field(default=60, ge=15, le=1440)
    document_collection_enabled: bool = True
    document_collection_interval_minutes: int = Field(default=1, ge=1, le=1440)
    document_collection_batch_size: int = Field(default=5, ge=1, le=50)
    document_max_bytes: int = Field(default=2_000_000, ge=10_000, le=10_000_000)
    document_max_chars: int = Field(default=60_000, ge=1000, le=200_000)
    ai_analysis_enabled: bool = False
    ai_analysis_interval_minutes: int = Field(default=5, ge=1, le=1440)
    ai_analysis_batch_size: int = Field(default=3, ge=1, le=50)
    ai_passage_chars: int = Field(default=3000, ge=500, le=6000)
    ai_max_passages: int = Field(default=3, ge=1, le=10)
    ai_input_budget_chars: int = Field(default=9000, ge=6000, le=60000)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_timeout_seconds: int = Field(default=600, ge=30, le=1800)
    scheduler_run_on_start: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
