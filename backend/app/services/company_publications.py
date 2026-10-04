from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select

from app.collectors.company_sec import FORMS, CompanyPublicationError, SECCompanyCollector
from app.core.config import get_settings
from app.models.collection_run import CollectionRun
from app.models.market import MarketInstrument
from app.models.source import Source
from app.services.ingestion import ArticleIngestionService


class CompanyPublicationService:
    def __init__(self, session):
        self.session = session

    async def latest(self, cik):
        return (
            await self.session.execute(
                select(CollectionRun)
                .join(Source)
                .where(Source.name == f"SEC company {cik}")
                .order_by(CollectionRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def status(self, instrument_id: UUID):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        run = await self.latest(instrument.cik) if instrument.cik else None
        return {
            "supported": bool(instrument.cik),
            "cik": instrument.cik,
            "scheduler_enabled": get_settings().company_publications_enabled,
            "source_url": f"https://data.sec.gov/submissions/CIK{instrument.cik}.json"
            if instrument.cik
            else None,
            "window_days": 365,
            "max_publications": 50,
            "forms": sorted(FORMS),
            "status": run.status if run else "pending",
            "started_at": run.started_at if run else None,
            "fetched_count": run.fetched_count if run else 0,
            "inserted_count": run.inserted_count if run else 0,
            "error": run.error_message if run else None,
            "notice": "Historique récent SEC, au plus 50 dépôts HTML sur 365 jours. "
            "Archives complémentaires et sociétés sans CIK hors couverture. "
            "L'acceptation SEC date la publication du dépôt, pas le fait économique.",
        }

    async def collect(self, instrument_id: UUID, *, trigger="manual", collector=None):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            raise ValueError("Titre introuvable.")
        if not instrument.cik:
            return {"status": "unsupported_identity"}
        await self.session.execute(select(func.pg_advisory_xact_lock(721905)))
        previous = await self.latest(instrument.cik)
        now = datetime.now(UTC)
        active = (
            await self.session.execute(
                select(CollectionRun.id)
                .join(Source)
                .where(
                    or_(Source.name.like("SEC company %"), Source.name.like("SEC financials %")),
                    CollectionRun.status == "running",
                    CollectionRun.started_at > now - timedelta(minutes=2),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if active:
            await self.session.commit()
            return {"status": "collection_in_progress"}
        delay = 60 if previous and previous.status == "success" else 5
        if previous and previous.started_at > now - timedelta(minutes=delay):
            await self.session.commit()
            return {"status": "cached_or_retry_pending"}
        collector = collector or SECCompanyCollector(instrument.cik, get_settings().sec_user_agent)
        if collector.cik != instrument.cik:
            await self.session.rollback()
            raise ValueError("Le collecteur ne correspond pas au CIK suivi.")
        try:
            stats = await ArticleIngestionService(self.session).run(collector, trigger=trigger)
        except CompanyPublicationError as exc:
            return {"status": "failed", "error": exc.code}
        return {"status": "success", **asdict(stats)}

    async def collect_scheduled(self, limit=5):
        ids = (
            (
                await self.session.execute(
                    select(func.min(cast(MarketInstrument.id, String)))
                    .outerjoin(Source, Source.name == ("SEC company " + MarketInstrument.cik))
                    .outerjoin(CollectionRun, CollectionRun.source_id == Source.id)
                    .where(MarketInstrument.cik.is_not(None))
                    .group_by(MarketInstrument.cik)
                    .order_by(
                        func.max(CollectionRun.started_at).asc().nulls_first(), MarketInstrument.cik
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        attempts = 0
        for identifier in ids:
            result = await self.collect(UUID(identifier), trigger="scheduled")
            if result["status"] in {"success", "failed"}:
                attempts += 1
            if attempts >= limit:
                break
        return {"attempts": attempts}
