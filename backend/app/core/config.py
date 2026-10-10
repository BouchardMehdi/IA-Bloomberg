from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    financial_results_enabled: bool = True
    wls_identity_enabled: bool = True
    wls_auto_watch_limit: int = Field(default=20, ge=0, le=100)
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
    ai_execution_mode: Literal["inline", "remote"] = "inline"
    ai_worker_token_sha256: SecretStr = SecretStr("")
    ai_remote_wait_seconds: int = Field(default=900, ge=30, le=7200)
    ai_analysis_interval_minutes: int = Field(default=5, ge=1, le=1440)
    ai_analysis_batch_size: int = Field(default=3, ge=1, le=50)
    ai_passage_chars: int = Field(default=3000, ge=500, le=6000)
    ai_max_passages: int = Field(default=3, ge=1, le=10)
    ai_input_budget_chars: int = Field(default=9000, ge=6000, le=60000)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_timeout_seconds: int = Field(default=600, ge=30, le=1800)
    scheduler_run_on_start: bool = True
    auth_enabled: bool = False
    auth_cookie_secure: bool = False
    international_news_enabled: bool = True
    alerts_enabled: bool = True
    data_inbox_directory: str = ""

    @model_validator(mode="after")
    def production_access(self):
        if self.environment == "production" and (not self.auth_enabled or not self.auth_cookie_secure):
            raise ValueError("Production requires AUTH_ENABLED=true and AUTH_COOKIE_SECURE=true.")
        if self.ai_execution_mode == "remote":
            digest = self.ai_worker_token_sha256.get_secret_value()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Remote AI requires a valid AI_WORKER_TOKEN_SHA256.")
        return self

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
