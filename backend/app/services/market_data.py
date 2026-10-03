from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.market.alpha_vantage import AlphaVantageClient, MarketDataError
from app.market.wls import eligibility
from app.models.entity_registry import EntityRegistry
from app.models.market import DailyPrice, MarketFetchRun, MarketInstrument
from app.schemas.market import InstrumentCreate
from app.services.usd_valuation import UsdValuationService


class MarketDataService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_instrument(self, request: InstrumentCreate) -> dict:
        registry = await self.session.get(EntityRegistry, "sec_tickers")
        if registry is None:
            raise ValueError("Référentiel SEC indisponible : synchroniser les identités d'abord.")
        matches = [
            r
            for r in registry.records
            if r["ticker"] == request.symbol
            and r["exchange"] in {"NYSE", "Nasdaq"}
            and (not request.exchange or r["exchange"] == request.exchange)
        ]
        matches = {(r["cik"], r["exchange"]): r for r in matches}
        if len(matches) != 1:
            raise ValueError("Ticker absent ou ambigu dans le référentiel NYSE/Nasdaq.")
        row = next(iter(matches.values()))
        instrument_id = (
            await self.session.execute(
                insert(MarketInstrument)
                .values(
                    symbol=request.symbol,
                    exchange=row["exchange"],
                    cik=row["cik"],
                    name=row["name"],
                    currency="USD",
                    registry_url=registry.source_url,
                    registry_observed_at=registry.observed_at,
                )
                .on_conflict_do_nothing(constraint="uq_market_symbol_exchange")
                .returning(MarketInstrument.id)
            )
        ).scalar_one_or_none()
        if instrument_id is None:
            instrument_id = (
                await self.session.execute(
                    select(MarketInstrument.id).where(
                        MarketInstrument.symbol == request.symbol,
                        MarketInstrument.exchange == row["exchange"],
                    )
                )
            ).scalar_one()
        await self.session.commit()
        return {"id": instrument_id, "symbol": request.symbol}

    async def list_instruments(self, instrument_id: UUID | None = None) -> dict:
        universe = await self.session.get(EntityRegistry, "wls_universe")
        query = select(MarketInstrument).order_by(MarketInstrument.symbol)
        if instrument_id is not None:
            query = query.where(MarketInstrument.id == instrument_id)
        instruments = (await self.session.execute(query)).scalars().all()
        items = []
        for instrument in instruments:
            price = await self.latest_price(instrument.id)
            run = (
                await self.session.execute(
                    select(MarketFetchRun)
                    .where(
                        MarketFetchRun.instrument_id == instrument.id,
                    )
                    .order_by(MarketFetchRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            items.append(
                {
                    "id": instrument.id,
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "exchange": instrument.exchange,
                    "cik": instrument.cik,
                    "currency": instrument.currency,
                    "isin": instrument.isin,
                    "bloomberg_symbol": instrument.bloomberg_symbol,
                    "identity_as_of": instrument.identity_as_of,
                    "quote_multiplier": instrument.quote_multiplier,
                    "price_provider": instrument.price_provider,
                    "usd_valuation": await UsdValuationService(self.session).quote(
                        instrument, price
                    ),
                    "registry_url": instrument.registry_url,
                    "registry_observed_at": instrument.registry_observed_at,
                    "latest_price": {
                        "close": price.close,
                        "date": price.session_date,
                        "source_url": price.source_url,
                        "fetched_at": price.fetched_at,
                        "stale": (datetime.now(UTC).date() - price.session_date).days
                        > get_settings().market_max_price_age_days,
                    }
                    if price
                    else None,
                    "collection_status": "manual"
                    if instrument.price_provider == "manual"
                    else run.status
                    if run
                    else "pending",
                    "error_code": run.error_code if run else None,
                    "wls_eligibility": eligibility(instrument, universe),
                }
            )
        return {
            "items": items,
            "provider_configured": bool(get_settings().alpha_vantage_api_key.get_secret_value()),
            "daily_request_budget": get_settings().market_daily_request_budget,
            "wls_imported": universe is not None,
            "wls_security_count": len(universe.records) if universe else 0,
        }

    async def latest_price(self, instrument_id: UUID) -> DailyPrice | None:
        return (
            await self.session.execute(
                select(DailyPrice)
                .where(
                    DailyPrice.instrument_id == instrument_id,
                )
                .order_by(DailyPrice.session_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def history(self, instrument_id: UUID, limit: int) -> dict | None:
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        prices = (
            (
                await self.session.execute(
                    select(DailyPrice)
                    .where(
                        DailyPrice.instrument_id == instrument_id,
                    )
                    .order_by(DailyPrice.session_date.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [
                {
                    "date": p.session_date,
                    "close": p.close,
                    "volume": p.volume,
                    "source_url": p.source_url,
                    "fetched_at": p.fetched_at,
                }
                for p in reversed(prices)
            ],
            "adjusted": False,
            "currency": instrument.currency,
            "quote_multiplier": instrument.quote_multiplier,
        }

    async def collect(self, client: AlphaVantageClient, limit: int = 5) -> dict:
        ids = (
            (
                await self.session.execute(
                    select(MarketInstrument.id)
                    .where(
                        MarketInstrument.price_provider == "alpha_vantage",
                        MarketInstrument.currency == "USD",
                        MarketInstrument.quote_multiplier == 1,
                    )
                    .outerjoin(
                        MarketFetchRun,
                        MarketFetchRun.instrument_id == MarketInstrument.id,
                    )
                    .group_by(MarketInstrument.id)
                    .order_by(
                        func.max(MarketFetchRun.started_at).asc().nulls_first(),
                        MarketInstrument.created_at,
                    )
                )
            )
            .scalars()
            .all()
        )
        stats = {"success": 0, "failed": 0, "skipped": 0}
        for instrument_id in ids:
            if stats["success"] + stats["failed"] >= limit:
                break
            # Persistent shared quota, including failed requests and concurrent workers.
            await self.session.execute(select(func.pg_advisory_xact_lock(721903)))
            now = datetime.now(UTC)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            attempts = (
                await self.session.execute(
                    select(func.count())
                    .select_from(MarketFetchRun)
                    .where(
                        MarketFetchRun.started_at >= day_start,
                    )
                )
            ).scalar_one()
            if attempts >= get_settings().market_daily_request_budget:
                await self.session.commit()
                break
            previous = (
                await self.session.execute(
                    select(MarketFetchRun)
                    .where(
                        MarketFetchRun.instrument_id == instrument_id,
                    )
                    .order_by(MarketFetchRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if previous and (
                (previous.status == "success" and previous.started_at >= day_start)
                or previous.started_at > now - timedelta(hours=1)
            ):
                stats["skipped"] += 1
                await self.session.commit()
                continue
            instrument = await self.session.get(MarketInstrument, instrument_id)
            symbol = instrument.symbol
            run = MarketFetchRun(instrument_id=instrument_id, started_at=now, status="running")
            self.session.add(run)
            await self.session.commit()
            try:
                records, url = await client.daily(symbol)
                for record in records:
                    await self.session.execute(
                        insert(DailyPrice)
                        .values(
                            instrument_id=instrument_id,
                            **record,
                            source_url=url,
                            fetched_at=datetime.now(UTC),
                        )
                        .on_conflict_do_update(
                            constraint="uq_daily_price",
                            set_={
                                "close": record["close"],
                                "volume": record["volume"],
                                "source_url": url,
                                "fetched_at": datetime.now(UTC),
                            },
                        )
                    )
                run.status = "success"
                stats["success"] += 1
            except MarketDataError as exc:
                run.status = "failed"
                run.error_code = str(exc)
                stats["failed"] += 1
            run.finished_at = datetime.now(UTC)
            await self.session.commit()
        return stats
