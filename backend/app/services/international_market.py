from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.models.market import DailyPrice, FxRate, MarketInstrument
from app.schemas.international import FxRateCreate, InternationalInstrumentCreate, LocalPriceCreate


class InternationalMarketService:
    def __init__(self, session):
        self.session = session

    async def rates(self) -> dict:
        rows = (
            (
                await self.session.execute(
                    select(FxRate)
                    .distinct(FxRate.currency)
                    .order_by(FxRate.currency, FxRate.rate_date.desc())
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [
                {
                    "currency": r.currency,
                    "date": r.rate_date,
                    "usd_per_unit": r.usd_per_unit,
                    "source_url": r.source_url,
                    "fetched_at": r.fetched_at,
                    "provider": r.provider,
                    "derivation": r.derivation,
                }
                for r in rows
            ]
        }

    async def add_instrument(self, request: InternationalInstrumentCreate) -> dict:
        # Identity and pricing conventions stay immutable once observations/orders can exist.
        candidates = [
            (MarketInstrument.symbol == request.symbol)
            & (MarketInstrument.exchange == request.exchange),
            (MarketInstrument.isin == request.isin)
            & (MarketInstrument.exchange == request.exchange),
        ]
        if request.bloomberg_symbol:
            candidates.append(MarketInstrument.bloomberg_symbol == request.bloomberg_symbol)
        rows = (
            (await self.session.execute(select(MarketInstrument).where(or_(*candidates))))
            .scalars()
            .all()
        )
        identity = request.model_dump(exclude={"source_url", "as_of", "asset_class"})
        if rows:
            if (
                len(rows) != 1
                or rows[0].price_provider != "manual"
                or any(getattr(rows[0], key) != value for key, value in identity.items())
            ):
                raise ValueError(
                    "Identité ou convention de cotation en conflit : vérifier la source."
                )
            return {"id": rows[0].id, "symbol": rows[0].symbol}
        instrument = MarketInstrument(
            **identity,
            price_provider="manual",
            registry_url=str(request.source_url),
            registry_observed_at=datetime.now(UTC),
            identity_as_of=request.as_of,
        )
        self.session.add(instrument)
        await self.session.commit()
        return {"id": instrument.id, "symbol": instrument.symbol}

    async def save_price(self, instrument_id, request: LocalPriceCreate) -> dict:
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            raise LookupError("Titre introuvable.")
        if instrument.price_provider != "manual":
            raise ValueError("Les titres SEC utilisent leur collecteur de cours dédié.")
        if (
            request.currency != instrument.currency
            or request.quote_multiplier != instrument.quote_multiplier
        ):
            raise ValueError("La devise ou l'unité du cours ne correspond pas au titre.")
        values = {
            "close": request.close,
            "volume": request.volume,
            "source_url": str(request.source_url),
            "fetched_at": datetime.now(UTC),
        }
        await self.session.execute(
            insert(DailyPrice)
            .values(
                instrument_id=instrument_id,
                session_date=request.as_of,
                **values,
            )
            .on_conflict_do_update(constraint="uq_daily_price", set_=values)
        )
        await self.session.commit()
        return {"instrument_id": instrument_id, "date": request.as_of}

    async def save_fx(self, request: FxRateCreate) -> dict:
        values = {
            "usd_per_unit": request.usd_per_unit,
            "source_url": str(request.source_url),
            "fetched_at": datetime.now(UTC),
            "provider": "manual",
            "derivation": None,
        }
        await self.session.execute(
            insert(FxRate)
            .values(
                currency=request.currency,
                rate_date=request.as_of,
                **values,
            )
            .on_conflict_do_update(constraint="uq_fx_currency_date", set_=values)
        )
        await self.session.commit()
        return {"currency": request.currency, "date": request.as_of}
