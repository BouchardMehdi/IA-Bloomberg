"""Persistent manual hypotheses with concurrency checks and an immutable audit trail."""
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.journal import DecisionRevision, ResearchDecision
from app.models.market import MarketInstrument
from app.models.portfolio import PaperPortfolio, PaperTrade

NOTICE = "Hypothèses rédigées par l’équipe, non certifiées par leur saisie. Aucun ordre ni recommandation automatique."


def fingerprint(data, decision_id=None):
    payload = data.model_dump(mode="json")
    return hashlib.sha256(json.dumps({"decision_id": str(decision_id), **payload}, sort_keys=True).encode()).hexdigest()


def serialize(revision):
    return {"id": revision.id, "version": revision.version, "author": revision.author,
            "recorded_at": revision.recorded_at, **revision.data}


class JournalService:
    def __init__(self, session):
        self.session = session

    async def validate_trade(self, request, decision):
        if request.trade_id:
            trade = await self.session.get(PaperTrade, request.trade_id)
            if not trade or trade.instrument_id != decision.instrument_id or trade.portfolio_id != decision.portfolio_id:
                raise ValueError("L’opération doit appartenir au titre et à la simulation de ce dossier.")

    async def save(self, request, author, decision_id=None):
        # Serializes retries of the same request, including initial creation.
        lock = int.from_bytes(hashlib.sha256(request.client_request_id.bytes).digest()[:8], "big", signed=True)
        await self.session.execute(select(func.pg_advisory_xact_lock(lock)))
        digest = fingerprint(request, decision_id)
        existing = (await self.session.execute(select(DecisionRevision).where(
            DecisionRevision.client_request_id == request.client_request_id))).scalar_one_or_none()
        if existing:
            if existing.fingerprint != digest or existing.author != author:
                raise ValueError("Identifiant de requête déjà utilisé avec un contenu différent.")
            await self.session.commit()
            return {"decision_id": existing.decision_id, "revision": serialize(existing), "inserted": False}
        now = datetime.now(UTC)
        if decision_id is None:
            if await self.session.get(MarketInstrument, request.instrument_id) is None:
                raise LookupError("Titre introuvable.")
            if request.portfolio_id and await self.session.get(PaperPortfolio, request.portfolio_id) is None:
                raise LookupError("Simulation introuvable.")
            decision = ResearchDecision(instrument_id=request.instrument_id, portfolio_id=request.portfolio_id, created_at=now)
            self.session.add(decision)
            await self.session.flush()
            version = 1
        else:
            decision = (await self.session.execute(select(ResearchDecision).where(
                ResearchDecision.id == decision_id).with_for_update())).scalar_one_or_none()
            if decision is None:
                raise LookupError("Dossier introuvable.")
            version = (await self.session.execute(select(func.max(DecisionRevision.version)).where(
                DecisionRevision.decision_id == decision.id))).scalar_one() + 1
            if request.expected_version != version - 1:
                raise ValueError("Le dossier a changé. Rechargez-le avant d’enregistrer une révision.")
        await self.validate_trade(request, decision)
        data = request.model_dump(mode="json", exclude={"client_request_id", "instrument_id", "portfolio_id", "expected_version"})
        revision = DecisionRevision(decision_id=decision.id, version=version, client_request_id=request.client_request_id,
            fingerprint=digest, author=author, recorded_at=now, data=data)
        self.session.add(revision)
        await self.session.commit()
        return {"decision_id": decision.id, "revision": serialize(revision), "inserted": True}

    async def detail(self, identifier, limit=20, offset=0):
        decision = await self.session.get(ResearchDecision, identifier)
        if not decision:
            raise LookupError("Dossier introuvable.")
        rows = (await self.session.execute(select(DecisionRevision).where(DecisionRevision.decision_id == identifier)
            .order_by(DecisionRevision.version.desc()).offset(offset).limit(limit + 1))).scalars().all()
        return {"id": decision.id, "instrument_id": decision.instrument_id, "portfolio_id": decision.portfolio_id,
            "created_at": decision.created_at, "items": [serialize(r) for r in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None, "notice": NOTICE}

    async def listing(self, status=None, instrument_id=None, portfolio_id=None, limit=20, offset=0, as_of=None):
        cutoff = as_of or datetime.now(UTC)
        ranked = select(DecisionRevision.id.label("revision_id"), func.row_number().over(
            partition_by=DecisionRevision.decision_id, order_by=DecisionRevision.version.desc()).label("rank"))
        ranked = ranked.where(DecisionRevision.recorded_at <= cutoff).subquery()
        query = select(ResearchDecision, DecisionRevision, MarketInstrument.symbol, MarketInstrument.exchange).join(
            DecisionRevision, DecisionRevision.decision_id == ResearchDecision.id).join(
            ranked, ranked.c.revision_id == DecisionRevision.id).join(
            MarketInstrument, MarketInstrument.id == ResearchDecision.instrument_id).where(ranked.c.rank == 1)
        if status:
            query = query.where(DecisionRevision.data["status"].astext == status)
        if instrument_id:
            query = query.where(ResearchDecision.instrument_id == instrument_id)
        if portfolio_id:
            query = query.where(ResearchDecision.portfolio_id == portfolio_id)
        total = (await self.session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        rows = (await self.session.execute(query.order_by(DecisionRevision.recorded_at.desc(), ResearchDecision.id)
            .offset(offset).limit(limit))).all()
        return {"items": [{"id": d.id, "instrument_id": d.instrument_id, "portfolio_id": d.portfolio_id,
            "symbol": symbol, "exchange": exchange, "latest": serialize(r)} for d, r, symbol, exchange in rows],
            "total": total, "notice": NOTICE}
