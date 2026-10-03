from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext

from sqlalchemy import select

from app.core.config import get_settings
from app.models.market import FxRate


def converted_price(close: Decimal, multiplier: Decimal, rate: Decimal) -> Decimal:
    for value in (close, multiplier, rate):
        if not value.is_finite() or value <= 0:
            raise ValueError("Cours, unité ou taux de conversion invalide.")
    with localcontext() as context:
        context.prec = 50
        raw = close * multiplier * rate
        if raw >= Decimal("100000000000000"):
            raise ValueError("Prix USD hors de la précision prise en charge.")
        result = raw.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if result <= 0 or result >= Decimal("100000000000000"):
        raise ValueError("Prix USD hors de la précision prise en charge.")
    return result


class UsdValuationService:
    def __init__(self, session):
        self.session = session

    async def quote(self, instrument, price, today: date | None = None) -> dict:
        today = today or datetime.now(UTC).date()
        if price is None:
            return {"status": "missing_price", "price_usd": None, "stale": True, "conversion": None}
        rate = None
        if instrument.currency != "USD":
            # Never combine a close with a later FX observation, including historic views.
            rate = (
                await self.session.execute(
                    select(FxRate)
                    .where(
                        FxRate.currency == instrument.currency,
                        FxRate.rate_date <= price.session_date,
                    )
                    .order_by(FxRate.rate_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if rate is None:
                return {
                    "status": "missing_fx",
                    "price_usd": None,
                    "stale": True,
                    "conversion": None,
                }
        price_stale = (
            not 0 <= (today - price.session_date).days <= get_settings().market_max_price_age_days
        )
        fx_stale = (
            rate is not None
            and not 0 <= (today - rate.rate_date).days <= get_settings().market_max_fx_age_days
        )
        conversion = {
            "local_close": str(price.close),
            "currency": instrument.currency,
            "quote_multiplier": str(instrument.quote_multiplier),
            "quote_date": price.session_date.isoformat(),
            "quote_source_url": price.source_url,
            "quote_fetched_at": price.fetched_at.isoformat(),
            "usd_per_unit": str(rate.usd_per_unit) if rate else "1",
            "fx_date": rate.rate_date.isoformat() if rate else None,
            "fx_source_url": rate.source_url if rate else None,
            "fx_fetched_at": rate.fetched_at.isoformat() if rate else None,
        }
        try:
            value = converted_price(
                price.close,
                instrument.quote_multiplier,
                rate.usd_per_unit if rate else Decimal("1"),
            )
        except ValueError:
            return {
                "status": "invalid_conversion",
                "price_usd": None,
                "stale": True,
                "conversion": conversion,
            }
        return {
            "status": "stale" if price_stale or fx_stale else "available",
            "price_usd": value,
            "stale": price_stale or fx_stale,
            "conversion": conversion,
        }
