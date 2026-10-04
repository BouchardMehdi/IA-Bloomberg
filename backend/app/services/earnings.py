import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.market.earnings_calendar import EarningsCalendarClient, validate_calendar_batch
from app.market.providers import MarketDataError, QuoteIdentity
from app.models.earnings import EarningsObservation
from app.models.market import MarketFetchRun, MarketInstrument
from app.schemas.earnings import EarningsInput


def compare_eps(result: dict, estimates: list[dict]) -> dict:
    if result["basis"] not in {"gaap_basic", "gaap_diluted"} or result["period_type"] == "unknown":
        return {
            "status": "not_comparable",
            "reason": "Périodicité ou convention de BPA inconnue ou ajustée.",
        }
    published = datetime.fromisoformat(result["published_at"])
    candidates = [
        item
        for item in estimates
        if item["fiscal_period_end"] == result["fiscal_period_end"]
        and item["period_type"] == result["period_type"]
        and item["currency"] == result["currency"]
        and item["basis"] == result["basis"]
        and item.get("published_at")
        and datetime.fromisoformat(item["published_at"]) < published
        # A forecast first collected after the result is not historical evidence.
        and datetime.fromisoformat(item["observed_at"]) < published
    ]
    if not candidates:
        return {
            "status": "not_comparable",
            "reason": "Aucune estimation compatible conservée avant la publication.",
        }
    latest = max(datetime.fromisoformat(item["published_at"]) for item in candidates)
    candidates = [
        item for item in candidates if datetime.fromisoformat(item["published_at"]) == latest
    ]
    if len(candidates) != 1:
        return {"status": "not_comparable", "reason": "Estimations simultanées ambiguës."}
    estimate = candidates[0]
    value = Decimal(estimate["eps"])
    delta = Decimal(result["eps"]) - value
    return {
        "status": "comparable",
        "estimate_id": estimate["id"],
        "estimate_source": estimate["source_url"],
        "estimate_published_at": estimate["published_at"],
        "delta": delta,
        "percent": (delta / abs(value) * 100).quantize(Decimal("0.01")) if value else None,
        "notice": "Écart à cette estimation fournie, pas à un consensus vérifié "
        "ni prévision de rendement.",
    }


class EarningsService:
    def __init__(self, session):
        self.session = session

    async def persist(self, instrument_id, data, provider, observed_at):
        fingerprint = hashlib.sha256(
            json.dumps({"provider": provider, **data}, sort_keys=True).encode()
        ).hexdigest()
        return (
            await self.session.execute(
                insert(EarningsObservation)
                .values(
                    instrument_id=instrument_id,
                    data=data,
                    provider=provider,
                    observed_at=observed_at,
                    fingerprint=fingerprint,
                )
                .on_conflict_do_nothing(constraint="uq_earnings_observation")
                .returning(EarningsObservation.id)
            )
        ).scalar_one_or_none()

    async def add(self, instrument_id: UUID, request: EarningsInput):
        if await self.session.get(MarketInstrument, instrument_id) is None:
            raise ValueError("Titre introuvable.")
        identifier = await self.persist(
            instrument_id, request.model_dump(mode="json"), "manual", datetime.now(UTC)
        )
        await self.session.commit()
        return {"inserted": identifier is not None, "id": identifier}

    async def detail(self, instrument_id: UUID, limit: int, offset: int):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        rows = (
            (
                await self.session.execute(
                    select(EarningsObservation)
                    .where(EarningsObservation.instrument_id == instrument_id)
                    .order_by(EarningsObservation.observed_at.desc(), EarningsObservation.id)
                    .offset(offset)
                    .limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )
        items = [
            {
                "id": row.id,
                "provider": row.provider,
                "observed_at": row.observed_at.isoformat(),
                **row.data,
            }
            for row in rows[:limit]
        ]
        # Comparisons deliberately use only the visible bounded page.
        estimates = [item for item in items if item["kind"] == "estimate"]
        for item in items:
            if item["kind"] == "reported":
                item["comparison"] = compare_eps(item, estimates)
        latest = (
            await self.session.execute(
                select(MarketFetchRun)
                .where(
                    MarketFetchRun.instrument_id == instrument_id,
                    MarketFetchRun.operation == "earnings_calendar",
                )
                .order_by(MarketFetchRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            "items": items,
            "next_offset": offset + limit if len(rows) > limit else None,
            "collection": {
                "configured": bool(get_settings().alpha_vantage_api_key.get_secret_value()),
                "supported": instrument.price_provider == "alpha_vantage"
                and instrument.exchange in {"NYSE", "Nasdaq"}
                and instrument.currency == "USD"
                and instrument.quote_multiplier == 1,
                "status": latest.status if latest else "pending",
                "error_code": latest.error_code if latest else None,
                "started_at": latest.started_at if latest else None,
                "retry_at": latest.retry_at if latest else None,
            },
            "notice": "Historique d'observations, dates prévisionnelles à confirmer. "
            "Aucun consensus ou rendement déduit. "
            "Comparaison limitée aux observations de cette page.",
        }

    async def collect(self, instrument_id: UUID, client: EarningsCalendarClient):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            raise ValueError("Titre introuvable.")
        if instrument.price_provider != "alpha_vantage" or not client.supports(
            QuoteIdentity.from_instrument(instrument)
        ):
            return {"status": "unsupported_listing"}
        policy = client.policy
        await self.session.execute(select(func.pg_advisory_xact_lock(721903)))
        now = datetime.now(UTC)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cooldown = (
            await self.session.execute(
                select(func.max(MarketFetchRun.retry_at)).where(
                    MarketFetchRun.provider == policy.provider,
                    MarketFetchRun.error_code.in_(["provider_quota", "provider_rejected_or_quota"]),
                    MarketFetchRun.retry_at > now,
                )
            )
        ).scalar_one()
        count = (
            await self.session.execute(
                select(func.count())
                .select_from(MarketFetchRun)
                .where(
                    MarketFetchRun.provider == policy.provider,
                    MarketFetchRun.started_at >= day,
                )
            )
        ).scalar_one()
        previous = (
            await self.session.execute(
                select(MarketFetchRun)
                .where(
                    MarketFetchRun.provider == policy.provider,
                    MarketFetchRun.instrument_id == instrument_id,
                    MarketFetchRun.operation == "earnings_calendar",
                )
                .order_by(MarketFetchRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        reason = (
            "provider_cooldown"
            if cooldown
            else "budget_exhausted"
            if count >= policy.daily_request_budget
            else None
        )
        calendar_count = (
            await self.session.execute(
                select(func.count())
                .select_from(MarketFetchRun)
                .where(
                    MarketFetchRun.provider == policy.provider,
                    MarketFetchRun.started_at >= day,
                    MarketFetchRun.operation == "earnings_calendar",
                )
            )
        ).scalar_one()
        if not reason and calendar_count >= max(1, policy.daily_request_budget // 4):
            reason = "calendar_budget_exhausted"
        if (
            not reason
            and previous
            and (
                (previous.status == "success" and previous.started_at >= day)
                or (previous.retry_at and previous.retry_at > now)
                or previous.started_at > now - timedelta(seconds=policy.retry_seconds)
            )
        ):
            reason = "cached_or_retry_pending"
        if reason:
            await self.session.commit()
            return {"status": reason}
        run = MarketFetchRun(
            instrument_id=instrument_id,
            provider=policy.provider,
            operation="earnings_calendar",
            status="running",
            started_at=now,
        )
        self.session.add(run)
        await self.session.commit()
        error = None
        try:
            async with asyncio.timeout(policy.timeout_seconds):
                records, source_url = await client.calendar(instrument.symbol)
                records = validate_calendar_batch(records, source_url, instrument.symbol)
        except MarketDataError as exc:
            error = exc.code
        except TimeoutError:
            error = "provider_timeout"
        except Exception:
            error = "provider_invalid_response"
        inserted = 0
        if error:
            run.status, run.error_code = "failed", error
            run.retry_at = policy.retry_at(error, datetime.now(UTC))
        else:
            for record in records:
                base = {
                    "fiscal_period_end": record.fiscal_period_end.isoformat(),
                    "report_date": record.report_date.isoformat(),
                    "source_url": source_url,
                    "published_at": None,
                    "basis": "unknown",
                    "period_type": "unknown",
                    "eps": None,
                    "currency": None,
                }
                if record.time_of_day is not None:
                    base["time_of_day"] = record.time_of_day
                inserted += bool(
                    await self.persist(
                        instrument_id, {**base, "kind": "schedule"}, policy.provider, now
                    )
                )
                if record.estimate is not None:
                    inserted += bool(
                        await self.persist(
                            instrument_id,
                            {
                                **base,
                                "kind": "estimate",
                                "eps": str(record.estimate),
                                "currency": record.currency,
                            },
                            policy.provider,
                            now,
                        )
                    )
            run.status = "success"
        run.finished_at = datetime.now(UTC)
        run.quote_context = {"record_count": len(records) if not error else 0, "horizon": "3month"}
        await self.session.commit()
        return {"status": run.status, "error_code": error, "inserted": inserted}

    async def collect_scheduled(self, client: EarningsCalendarClient, limit: int = 2):
        ids = (
            (
                await self.session.execute(
                    select(MarketInstrument.id)
                    .where(MarketInstrument.price_provider == client.policy.provider)
                    .outerjoin(
                        MarketFetchRun,
                        (MarketFetchRun.instrument_id == MarketInstrument.id)
                        & (MarketFetchRun.operation == "earnings_calendar"),
                    )
                    .group_by(MarketInstrument.id)
                    .order_by(
                        func.max(MarketFetchRun.started_at).asc().nulls_first(), MarketInstrument.id
                    )
                )
            )
            .scalars()
            .all()
        )
        attempts = 0
        for identifier in ids:
            result = await self.collect(identifier, client)
            if result["status"] in {"success", "failed"}:
                attempts += 1
            if attempts >= limit or result["status"] in {
                "budget_exhausted",
                "calendar_budget_exhausted",
                "provider_cooldown",
            }:
                break
        return {"attempts": attempts}
