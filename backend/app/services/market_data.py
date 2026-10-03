import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.market.provider_registry import price_provider_catalog
from app.market.providers import MarketDataError, PriceProvider, QuoteIdentity, validate_batch
from app.market.wls import eligibility
from app.models.entity_registry import EntityRegistry
from app.models.market import DailyPrice, MarketFetchRun, MarketInstrument
from app.schemas.market import InstrumentCreate
from app.services.usd_valuation import UsdValuationService


class MarketDataService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def collection_status(self) -> dict:
        now = datetime.now(UTC)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        items = []
        for descriptor in price_provider_catalog(get_settings()):
            provider = descriptor["provider"]
            attempts = (
                await self.session.execute(
                    select(func.count())
                    .select_from(MarketFetchRun)
                    .where(
                        MarketFetchRun.provider == provider,
                        MarketFetchRun.started_at >= day_start,
                    )
                )
            ).scalar_one()
            blocked_until = (
                await self.session.execute(
                    select(func.max(MarketFetchRun.retry_at)).where(
                        MarketFetchRun.provider == provider,
                        MarketFetchRun.status == "failed",
                        MarketFetchRun.error_code.in_(
                            ["provider_quota", "provider_rejected_or_quota"]
                        ),
                        MarketFetchRun.retry_at > now,
                    )
                )
            ).scalar_one()
            latest = (
                await self.session.execute(
                    select(MarketFetchRun)
                    .where(
                        MarketFetchRun.provider == provider,
                    )
                    .order_by(MarketFetchRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            items.append(
                {
                    **descriptor,
                    "attempts_today": attempts,
                    "remaining_today": max(0, descriptor["daily_request_budget"] - attempts),
                    "blocked_until": blocked_until,
                    "latest_run": {
                        "instrument_id": latest.instrument_id,
                        "status": latest.status,
                        "started_at": latest.started_at,
                        "finished_at": latest.finished_at,
                        "error_code": latest.error_code,
                        "retry_at": latest.retry_at,
                    }
                    if latest
                    else None,
                }
            )
        return {
            "items": items,
            "quota_day": day_start.date(),
            "quota_timezone": "UTC",
            "international_quotes_connected": False,
        }

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
                        MarketFetchRun.provider == instrument.price_provider,
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
                        "provider": price.provider,
                        "quote_context": price.quote_context,
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
                    "retry_at": run.retry_at if run else None,
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
                    "provider": p.provider,
                    "quote_context": p.quote_context,
                }
                for p in reversed(prices)
            ],
            "adjusted": False,
            "currency": instrument.currency,
            "quote_multiplier": instrument.quote_multiplier,
        }

    async def collect(self, client: PriceProvider, limit: int = 5) -> dict:
        policy = client.policy
        ids = (
            (
                await self.session.execute(
                    select(MarketInstrument.id)
                    .where(
                        MarketInstrument.price_provider == policy.provider,
                    )
                    .outerjoin(
                        MarketFetchRun,
                        (MarketFetchRun.instrument_id == MarketInstrument.id)
                        & (MarketFetchRun.provider == policy.provider),
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
        stats = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "provider": policy.provider,
            "blocked_until": None,
            "budget_exhausted": False,
        }
        for instrument_id in ids:
            if stats["success"] + stats["failed"] >= limit:
                break
            # Persistent shared quota, including failed requests and concurrent workers.
            await self.session.execute(select(func.pg_advisory_xact_lock(721903)))
            now = datetime.now(UTC)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            cooldown = (
                await self.session.execute(
                    select(func.max(MarketFetchRun.retry_at)).where(
                        MarketFetchRun.provider == policy.provider,
                        MarketFetchRun.status == "failed",
                        MarketFetchRun.error_code.in_(
                            ["provider_quota", "provider_rejected_or_quota"]
                        ),
                        MarketFetchRun.retry_at > now,
                    )
                )
            ).scalar_one()
            if cooldown:
                stats["blocked_until"] = cooldown
                await self.session.commit()
                break
            attempts = (
                await self.session.execute(
                    select(func.count())
                    .select_from(MarketFetchRun)
                    .where(
                        MarketFetchRun.started_at >= day_start,
                        MarketFetchRun.provider == policy.provider,
                    )
                )
            ).scalar_one()
            if attempts >= policy.daily_request_budget:
                stats["budget_exhausted"] = True
                await self.session.commit()
                break
            previous = (
                await self.session.execute(
                    select(MarketFetchRun)
                    .where(
                        MarketFetchRun.instrument_id == instrument_id,
                        MarketFetchRun.provider == policy.provider,
                    )
                    .order_by(MarketFetchRun.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if previous and (
                (previous.status == "success" and previous.started_at >= day_start)
                or (previous.retry_at is not None and previous.retry_at > now)
                or previous.started_at > now - timedelta(seconds=policy.retry_seconds)
            ):
                stats["skipped"] += 1
                await self.session.commit()
                continue
            instrument = await self.session.get(MarketInstrument, instrument_id)
            identity = QuoteIdentity.from_instrument(instrument)
            if not client.supports(identity):
                stats["skipped"] += 1
                await self.session.commit()
                continue
            run = MarketFetchRun(
                instrument_id=instrument_id,
                started_at=now,
                status="running",
                provider=policy.provider,
                quote_context=identity.model_dump(mode="json"),
            )
            self.session.add(run)
            await self.session.commit()
            error = None
            try:
                async with asyncio.timeout(policy.timeout_seconds):
                    batch = validate_batch(await client.fetch(identity), identity, policy.provider)
            except MarketDataError as exc:
                error = exc.code
            except TimeoutError:
                error = "provider_timeout"
            except ValueError:
                error = "invalid_quote_batch"
            except Exception:
                # Adapter exceptions are untrusted: never log their text or request URL.
                error = "provider_internal_error"
            if error:
                run.status = "failed"
                run.error_code = error
                run.retry_at = policy.retry_at(error, datetime.now(UTC))
                stats["failed"] += 1
            else:
                fetched_at = datetime.now(UTC)
                run.quote_context = batch.context()
                # All validation precedes writes. Database errors propagate and roll back
                # the complete batch; the durable reservation still counts against quota.
                for record in batch.records:
                    values = {
                        "close": record.close,
                        "volume": record.volume,
                        "source_url": str(batch.source_url),
                        "fetched_at": fetched_at,
                        "provider": policy.provider,
                        "quote_context": batch.context(),
                    }
                    await self.session.execute(
                        insert(DailyPrice)
                        .values(
                            instrument_id=instrument_id,
                            session_date=record.session_date,
                            **values,
                        )
                        .on_conflict_do_update(
                            constraint="uq_daily_price",
                            set_=values,
                        )
                    )
                run.status = "success"
                stats["success"] += 1
            run.finished_at = datetime.now(UTC)
            await self.session.commit()
            if error in {"provider_quota", "provider_rejected_or_quota"}:
                stats["blocked_until"] = run.retry_at
                break
        return stats
