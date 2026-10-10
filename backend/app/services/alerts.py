"""Bounded cursor scans, immutable deduplication and per-reader receipts."""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from app.models.collection_run import CollectionRun
from app.models.company import EventCompany
from app.models.earnings import EarningsObservation
from app.models.event import Event, EventArticle
from app.models.market import FxCollectionRun, MarketFetchRun, MarketInstrument
from app.models.source import Source
from app.models.workspace import AlertReceipt, WorkspaceAlert, WorkspaceCursor
from app.services.instrument_research import research_card


class AlertService:
    def __init__(self, session):
        self.session = session

    async def emit(self, key, kind, data, instrument_id=None):
        return (await self.session.execute(insert(WorkspaceAlert).values(
            dedup_key=key, kind=kind, data=data, instrument_id=instrument_id,
            created_at=datetime.now(UTC),
        ).on_conflict_do_nothing(index_elements=[WorkspaceAlert.dedup_key])
          .returning(WorkspaceAlert.id))).scalar_one_or_none()

    async def scan(self, name, model, clock, now, options=()):
        cursor = await self.session.get(WorkspaceCursor, name)
        floor = now - timedelta(days=30)
        after = clock >= floor
        if cursor:
            stamp = datetime.fromisoformat(cursor.data["time"])
            after = and_(after, or_(clock > stamp, and_(clock == stamp, model.id > UUID(cursor.data["id"]))))
        rows = (await self.session.execute(select(model).where(after, clock <= now)
                .options(*options).order_by(clock, model.id).limit(100))).scalars().all()
        if rows:
            last = rows[-1]
            data = {"time": getattr(last, clock.key).isoformat(), "id": str(last.id)}
            await self.session.execute(insert(WorkspaceCursor).values(name=name, data=data)
                .on_conflict_do_update(index_elements=[WorkspaceCursor.name], set_={"data": data}))
        return rows

    async def collect(self):
        # Only one scheduler/manual scan writes cursor advances at a time.
        await self.session.execute(select(func.pg_advisory_xact_lock(721931)))
        now = datetime.now(UTC)
        instruments = (await self.session.execute(select(MarketInstrument))).scalars().all()
        ids = {i.id for i in instruments}
        count = 0
        events = await self.scan("alert_events", Event, Event.updated_at, now, (
            selectinload(Event.company_links).selectinload(EventCompany.company),
            selectinload(Event.article_links).selectinload(EventArticle.article),
            selectinload(Event.fact_analysis_run),
        ))
        for event in events:
            if event.merged_into_event_id:
                continue
            if not event.parent_event_id and event.event_type == "official_publication":
                dated = [link.article for link in event.article_links if link.article.published_at
                         and link.article.published_at <= now]
                if dated:
                    article = dated[0]
                    count += bool(await self.emit(f"official:{event.id}", "publication", {
                        "title": event.title, "message": "Publication officielle internationale. Aucun lien avec une cotation suivie n’est déduit automatiquement.",
                        "url": article.url, "published_at": article.published_at.isoformat(), "page": "/",
                    }))
            for instrument in instruments:
                card = research_card(event, instrument)
                if not card:
                    continue
                sources = [s for s in card["sources"] if s["published_at"] <= now]
                if not sources:
                    continue
                source = sources[0]
                count += bool(await self.emit(f"event:{event.id}:{instrument.id}", card["kind"], {
                    "title": f"{instrument.symbol} · {card['title']}",
                    "message": "Nouveau document ou fait rapproché. Le contexte de l’émetteur ne prouve pas un impact sur cette cotation.",
                    "url": source["url"], "published_at": source["published_at"].isoformat(),
                    "relationship": card["relationship"], "page": "/analysis",
                }, instrument.id))
        for row in await self.scan("alert_earnings", EarningsObservation, EarningsObservation.observed_at, now):
            if row.instrument_id not in ids:
                continue
            d = row.data
            # Each changed observation remains distinct; no obsolete forecast is reactivated.
            count += bool(await self.emit(f"earnings:{row.id}", "calendar", {
                "title": "Nouvelle observation du calendrier",
                "message": f"{d['kind']} · date annoncée {d['report_date']} · période {d['fiscal_period_end']}. Consulter l’historique pour les déplacements et résultats.",
                "url": d["source_url"], "published_at": d.get("published_at"),
                "page": "/calendar",
            }, row.instrument_id))
        sources = {s.id: s for s in (await self.session.execute(select(Source))).scalars()}
        for row in await self.scan("alert_collections", CollectionRun, CollectionRun.finished_at, now):
            if row.status != "failed":
                continue
            source = sources.get(row.source_id)
            count += bool(await self.emit(f"collection:{row.id}", "collection_error", {
                "title": f"Collecte échouée · {source.name if source else 'source'}",
                "message": "La tentative a échoué. Les documents précédemment collectés sont conservés.",
                "url": source.url if source else None, "published_at": None, "page": "/",
            }))
        for row in await self.scan("alert_market", MarketFetchRun, MarketFetchRun.finished_at, now):
            if row.status != "failed" or row.instrument_id not in ids:
                continue
            count += bool(await self.emit(f"market:{row.id}", "collection_error", {
                "title": f"Collecte {row.operation} échouée",
                "message": f"Code fournisseur : {row.error_code or 'indisponible'}. Le quota et le délai de reprise restent respectés.",
                "url": None, "published_at": None, "page": "/coverage",
            }, row.instrument_id))
        for row in await self.scan("alert_fx", FxCollectionRun, FxCollectionRun.finished_at, now):
            if row.status == "failed":
                count += bool(await self.emit(f"fx:{row.id}", "collection_error", {
                    "title": "Collecte des taux BCE échouée", "message": "Les taux précédents sont conservés.",
                    "url": row.source_url, "published_at": None, "page": "/international",
                }))
        await self.session.commit()
        return {"inserted": count, "batch_size": 100, "initial_lookback_days": 30}

    async def detail(self, reader, kind=None, unread=False, limit=20, offset=0):
        read = select(AlertReceipt.alert_id).where(AlertReceipt.reader == reader)
        clauses = []
        if kind:
            clauses.append(WorkspaceAlert.kind == kind)
        if unread:
            clauses.append(WorkspaceAlert.id.not_in(read))
        total = (await self.session.execute(select(func.count()).select_from(WorkspaceAlert).where(*clauses))).scalar_one()
        unread_count = (await self.session.execute(select(func.count()).select_from(WorkspaceAlert)
                        .where(WorkspaceAlert.id.not_in(read)))).scalar_one()
        rows = (await self.session.execute(select(WorkspaceAlert).where(*clauses)
                .order_by(WorkspaceAlert.created_at.desc(), WorkspaceAlert.id).offset(offset).limit(limit))).scalars().all()
        read_ids = set((await self.session.execute(read.where(AlertReceipt.alert_id.in_([r.id for r in rows])))).scalars())
        return {"items": [{"id": r.id, "kind": r.kind, "instrument_id": r.instrument_id,
                           "created_at": r.created_at, "read": r.id in read_ids, **r.data} for r in rows],
                "total": total, "unread_count": unread_count,
                "next_offset": offset + limit if offset + limit < total else None,
                "notice": "Alertes documentaires et techniques, sans signal d’achat. Historique initial limité aux 30 derniers jours ; traitement par lots de 100."}

    async def mark_read(self, reader, identifier):
        if await self.session.get(WorkspaceAlert, identifier) is None:
            raise LookupError("Alerte introuvable.")
        await self.session.execute(insert(AlertReceipt).values(reader=reader, alert_id=identifier)
            .on_conflict_do_nothing())
        await self.session.commit()
        return {"ok": True}
