"""Read-only collection health: observed history, explicit cadence and earliest retries."""
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.models.article import Article
from app.models.collection_run import CollectionRun
from app.models.market import DailyPrice, FxCollectionRun, MarketFetchRun, MarketInstrument
from app.models.source import Source
from app.models.workspace import WorkspaceCursor


def safe_error(value):
    return value if value and re.fullmatch(r"[a-z][a-z0-9_]{1,70}", value) else "collecte_echouee" if value else None


def health_state(last, success, now, interval, enabled=True):
    if not enabled:
        return "disabled"
    if not last:
        return "pending"
    if last.status == "running":
        return "interrupted" if now - last.started_at > timedelta(minutes=max(interval * 2, 10)) else "running"
    if last.status == "failed":
        return "failed"
    if not success or now - success > timedelta(minutes=max(interval * 3, 60)):
        return "stale"
    return "healthy"


def source_policy(name, settings):
    if name.startswith("SEC financials "):
        return settings.financial_results_enabled, 1440, 5
    if name.startswith("SEC company "):
        return settings.company_publications_enabled, 60, 5
    if name == "European Central Bank":
        return True, settings.ecb_collection_interval_minutes, settings.ecb_collection_interval_minutes
    if name == "Federal Reserve Board":
        return True, settings.fed_collection_interval_minutes, settings.fed_collection_interval_minutes
    if name == "SEC EDGAR 8-K":
        return True, settings.sec_collection_interval_minutes, settings.sec_collection_interval_minutes
    return settings.international_news_enabled, 30, 30


async def heartbeat(session):
    data = {"observed_at": datetime.now(UTC).isoformat(), "next_workspace_cycle_after_seconds": 60}
    await session.execute(insert(WorkspaceCursor).values(name="scheduler_health", data=data)
        .on_conflict_do_update(index_elements=[WorkspaceCursor.name], set_={"data": data}))
    await session.commit()


class CollectionHealthService:
    def __init__(self, session):
        self.session = session

    async def detail(self, limit=20, offset=0, family="sources"):
        now, settings = datetime.now(UTC), get_settings()
        cursor = await self.session.get(WorkspaceCursor, "scheduler_health")
        stamp = datetime.fromisoformat(cursor.data["observed_at"]) if cursor else None
        scheduler = {"last_seen_at": stamp, "status": "recent" if stamp and now - stamp < timedelta(minutes=5) else "unknown_or_stale"}
        if family == "sources":
            total = (await self.session.execute(select(func.count()).select_from(Source))).scalar_one()
            sources = (await self.session.execute(select(Source).order_by(Source.name, Source.id).offset(offset).limit(limit))).scalars().all()
            items = []
            for source in sources:
                last = (await self.session.execute(select(CollectionRun).where(CollectionRun.source_id == source.id)
                    .order_by(CollectionRun.started_at.desc(), CollectionRun.id).limit(1))).scalar_one_or_none()
                success = (await self.session.execute(select(func.max(CollectionRun.finished_at)).where(
                    CollectionRun.source_id == source.id, CollectionRun.status == "success"))).scalar_one()
                publication, fetched = (await self.session.execute(select(func.max(Article.published_at), func.max(Article.fetched_at))
                    .where(Article.source_id == source.id))).one()
                enabled, interval, retry = source_policy(source.name, settings)
                enabled = enabled and source.enabled
                next_at = last.started_at + timedelta(minutes=retry if last.status == "failed" else interval) if last and enabled else None
                items.append({"id": source.id, "name": source.name, "url": source.url,
                    "status": health_state(last, success, now, interval, enabled),
                    "last_attempt_at": last.started_at if last else None, "last_success_at": success,
                    "last_publication_at": publication, "last_observed_at": fetched,
                    "next_eligible_at": next_at, "cadence_minutes": interval,
                    "error_code": safe_error(last.error_message) if last and last.status == "failed" else None,
                    "fetched_count": last.fetched_count if last else 0,
                    "notice": "Cache et reprise au plus tôt ; passage réel soumis au scheduler, aux réservations et aux lots."})
        elif family == "market":
            ranked = select(MarketFetchRun.id, func.row_number().over(partition_by=(MarketFetchRun.instrument_id, MarketFetchRun.operation, MarketFetchRun.provider),
                order_by=(MarketFetchRun.started_at.desc(), MarketFetchRun.id)).label("rank")).subquery()
            query = select(MarketFetchRun, MarketInstrument).join(ranked, ranked.c.id == MarketFetchRun.id).join(
                MarketInstrument, MarketInstrument.id == MarketFetchRun.instrument_id).where(ranked.c.rank == 1)
            total = (await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
            rows = (await self.session.execute(query.order_by(MarketInstrument.symbol, MarketFetchRun.operation).offset(offset).limit(limit))).all()
            items = []
            for run, instrument in rows:
                success = (await self.session.execute(select(func.max(MarketFetchRun.finished_at)).where(
                    MarketFetchRun.instrument_id == instrument.id, MarketFetchRun.operation == run.operation,
                    MarketFetchRun.provider == run.provider, MarketFetchRun.status == "success"))).scalar_one()
                price_date = (await self.session.execute(select(func.max(DailyPrice.session_date)).where(DailyPrice.instrument_id == instrument.id))).scalar_one()
                enabled = bool(settings.alpha_vantage_api_key.get_secret_value()) and (run.operation != "earnings_calendar" or settings.earnings_calendar_enabled)
                items.append({"id": run.id, "name": f"{instrument.symbol} · {instrument.exchange} · {run.operation}",
                    "status": health_state(run, success, now, 1440, enabled), "last_attempt_at": run.started_at,
                    "last_success_at": success, "last_publication_at": None, "last_observed_at": run.finished_at,
                    "price_date": price_date, "price_stale": price_date is None or (now.date() - price_date).days > settings.market_max_price_age_days,
                    "next_eligible_at": run.retry_at, "cadence_minutes": 60, "error_code": safe_error(run.error_code),
                    "notice": "Reprise persistante du fournisseur ; quota partagé, pas de nouvelle requête déclenchée ici."})
        else:
            total = 1
            run = (await self.session.execute(select(FxCollectionRun).order_by(FxCollectionRun.started_at.desc()).limit(1))).scalar_one_or_none()
            success = (await self.session.execute(select(func.max(FxCollectionRun.finished_at)).where(FxCollectionRun.status == "success"))).scalar_one()
            interval = settings.fx_collection_interval_minutes
            items = [{"id": "ecb-fx", "name": "Taux de référence BCE", "url": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
                "status": health_state(run, success, now, interval, settings.fx_collection_enabled),
                "last_attempt_at": run.started_at if run else None, "last_success_at": success,
                "last_publication_at": None, "reference_date": run.latest_reference_date if run else None,
                "last_observed_at": run.finished_at if run else None,
                "next_eligible_at": run.started_at + timedelta(minutes=interval) if run and settings.fx_collection_enabled else None,
                "cadence_minutes": interval, "error_code": safe_error(run.error_code) if run else None,
                "notice": "Date de référence distincte de la consultation ; taux de référence, pas d’exécution Bloomberg."}] if offset == 0 else []
        return {"generated_at": now, "scheduler": scheduler, "items": items, "total": total,
            "notice": "État technique observé. Une collecte réussie ne prouve ni fraîcheur de tous les chiffres ni couverture complète. Les sources jamais consultées ne figurent pas encore dans cet historique."}
