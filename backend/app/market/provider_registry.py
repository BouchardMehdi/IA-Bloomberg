"""Only explicitly configured and implemented providers are activated."""

from app.core.config import Settings
from app.market.alpha_vantage import AlphaVantageClient
from app.market.providers import PriceProvider


def configured_price_providers(settings: Settings) -> tuple[PriceProvider, ...]:
    key = settings.alpha_vantage_api_key.get_secret_value()
    if not key:
        return ()
    return (AlphaVantageClient(key, daily_request_budget=settings.market_daily_request_budget),)


def price_provider_catalog(settings: Settings) -> list[dict]:
    return [
        {
            "provider": "alpha_vantage",
            "configured": bool(settings.alpha_vantage_api_key.get_secret_value()),
            "daily_request_budget": settings.market_daily_request_budget,
            "exchanges": ["NYSE", "Nasdaq"],
            "currencies": ["USD"],
            "quote_multipliers": ["1"],
            "adjusted": False,
            "international": "explicit_sourced_mapping_required",
        }
    ]
