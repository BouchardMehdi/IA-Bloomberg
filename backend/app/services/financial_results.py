import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.collectors.company_sec import CompanyPublicationError
from app.core.config import get_settings
from app.market.sec_financials import (
    COLLECTOR_VERSION,
    CONCEPTS,
    INSTANT_CONCEPTS,
    METRIC_LABELS,
    FinancialRecord,
    SecFinancialClient,
)
from app.models.collection_run import CollectionRun
from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument
from app.models.source import Source
from app.repositories.collection_runs import CollectionRunRepository


def eps_comparison_guard(record: dict) -> dict | None:
    if not record["metric"].startswith("eps_"):
        return None
    return {
        "status": "not_comparable",
        "reasons": [
            "BPA de l'émetteur : correspondance avec l'unité économique de ce titre non vérifiée.",
            "Les estimations du calendrier ne fournissent ni début de période "
            "ni convention GAAP vérifiée.",
            "Le dépôt peut reprendre une période déjà publiée ; "
            "la première annonce des résultats doit être identifiée.",
        ],
    }


class FinancialResultsService:
    def __init__(self, session):
        self.session = session

    async def latest(self, cik):
        return (
            await self.session.execute(
                select(CollectionRun)
                .join(Source)
                .where(Source.name == f"SEC financials {cik}")
                .order_by(CollectionRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def detail(self, instrument_id: UUID, limit: int, offset: int):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        rows = []
        run = None
        metrics = []
        if instrument.cik:
            run = await self.latest(instrument.cik)
            rows = (
                (
                    await self.session.execute(
                        select(FinancialFact)
                        .where(FinancialFact.cik == instrument.cik)
                        .order_by(
                            FinancialFact.period_end.desc(),
                            FinancialFact.filed_on.desc(),
                            FinancialFact.id,
                        )
                        .offset(offset)
                        .limit(limit + 1)
                    )
                )
                .scalars()
                .all()
            )
            metrics = (
                (
                    await self.session.execute(
                        select(FinancialFact.data["metric"].astext)
                        .where(FinancialFact.cik == instrument.cik)
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
        items = [
            {
                "id": row.id,
                "observed_at": row.observed_at,
                **row.data,
                "period_type": "instant" if row.data["concept"] in INSTANT_CONCEPTS else "duration",
                "comparison": eps_comparison_guard(row.data),
            }
            for row in rows[:limit]
        ]
        return {
            "items": items,
            "next_offset": offset + limit if len(rows) > limit else None,
            "available_metrics": sorted(metrics),
            "supported_metrics": sorted(set(CONCEPTS.values())),
            "metric_labels": METRIC_LABELS,
            "collection": {
                "supported": bool(instrument.cik),
                "cik": instrument.cik,
                "scheduler_enabled": get_settings().financial_results_enabled,
                "status": run.status if run else "pending",
                "coverage_current": bool(run and run.collector_version == COLLECTOR_VERSION),
                "error": run.error_message if run else None,
                "started_at": run.started_at if run else None,
                "fetched_count": run.fetched_count if run else 0,
                "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{instrument.cik}.json"
                if instrument.cik
                else None,
            },
            "notice": "Observations US-GAAP de l'émetteur, pas chiffres propres à la cotation. "
            "Historique conservé sans fusion des définitions ou dépôts. "
            "fp/fy décrivent le dépôt, pas la durée de chaque mesure. "
            "Collecte bornée : dépôts des 365 derniers jours, fins de période sur 730 jours, "
            "2 000 observations maximum par réponse. IFRS et extensions non couverts.",
        }

    async def collect(self, instrument_id: UUID, *, client=None, trigger="manual"):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            raise ValueError("Titre introuvable.")
        if not instrument.cik:
            return {"status": "unsupported_identity"}
        client = client or SecFinancialClient(instrument.cik, get_settings().sec_user_agent)
        expected_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{instrument.cik}.json"
        if client.cik != instrument.cik or client.source_url != expected_url:
            raise ValueError("CIK du fournisseur incompatible.")
        await self.session.execute(select(func.pg_advisory_xact_lock(721905)))
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
        previous = await self.latest(instrument.cik)
        if active:
            await self.session.commit()
            return {"status": "collection_in_progress"}
        if (
            previous
            and (previous.status != "success" or previous.collector_version == COLLECTOR_VERSION)
            and previous.started_at
            > now - timedelta(minutes=1440 if previous.status == "success" else 5)
        ):
            await self.session.commit()
            return {"status": "cached_or_retry_pending"}
        source_id = (
            await self.session.execute(
                insert(Source)
                .values(
                    name=f"SEC financials {instrument.cik}",
                    source_type="regulator",
                    url=client.source_url,
                    country="US",
                    region="NORTH_AMERICA",
                    reliability_score=1.0,
                    enabled=True,
                )
                .on_conflict_do_update(
                    index_elements=[Source.name], set_={"url": client.source_url}
                )
                .returning(Source.id)
            )
        ).scalar_one()
        repository = CollectionRunRepository(self.session)
        run_id = await repository.start(source_id, trigger, now)
        await self.session.execute(
            update(CollectionRun)
            .where(CollectionRun.id == run_id)
            .values(collector_version=COLLECTOR_VERSION)
        )
        await self.session.commit()
        started = time.perf_counter()
        try:
            records = await client.fetch()
            if len(records) > 2000:
                raise CompanyPublicationError("sec_invalid_response")
            records = [FinancialRecord.model_validate(record.model_dump()) for record in records]
        except CompanyPublicationError as exc:
            error = exc.code
        except Exception:
            error = "sec_invalid_response"
        else:
            error = None
        if error:
            await self.session.rollback()
            await repository.fail(
                run_id,
                finished_at=datetime.now(UTC),
                duration_ms=round((time.perf_counter() - started) * 1000),
                error_message=error,
            )
            await self.session.commit()
            return {"status": "failed", "error": error}
        inserted = 0
        for record in records:
            data = record.model_dump(mode="json")
            # Filing date is date-only; never invent a publication time.
            data["source_url"] = f"https://www.sec.gov/Archives/edgar/data/{int(instrument.cik)}/"
            data["source_url"] += (
                f"{record.accession.replace('-', '')}/{record.accession}-index.html"
            )
            data["data_source_url"] = client.source_url
            digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
            identifier = (
                await self.session.execute(
                    insert(FinancialFact)
                    .values(
                        cik=instrument.cik,
                        fingerprint=digest,
                        period_end=record.end,
                        filed_on=record.filed,
                        observed_at=now,
                        data=data,
                    )
                    .on_conflict_do_nothing(constraint="uq_financial_fact")
                    .returning(FinancialFact.id)
                )
            ).scalar_one_or_none()
            inserted += identifier is not None
        await repository.succeed(
            run_id,
            finished_at=datetime.now(UTC),
            duration_ms=round((time.perf_counter() - started) * 1000),
            fetched=len(records),
            inserted=inserted,
            duplicates=len(records) - inserted,
        )
        await self.session.commit()
        return {"status": "success", "inserted": inserted, "fetched": len(records)}

    async def collect_scheduled(self, limit=3):
        identifiers = (
            (
                await self.session.execute(
                    select(func.min(cast(MarketInstrument.id, String)))
                    .outerjoin(Source, Source.name == ("SEC financials " + MarketInstrument.cik))
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
        for identifier in identifiers:
            result = await self.collect(UUID(identifier), trigger="scheduled")
            attempts += result["status"] in {"success", "failed"}
        return {"attempts": attempts}
