"""Daily factual reading list, generated without LLM or financial forecasts."""
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from app.models.earnings import EarningsObservation
from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument
from app.models.portfolio import PaperPortfolio, PaperPosition
from app.models.workspace import WorkspaceAlert
from app.services.journal import JournalService
from app.services.opportunity import upcoming_events


class BriefingService:
    def __init__(self, session):
        self.session = session

    async def detail(self, day: date, portfolio_id=None, limit=20, offset=0, held_only=False):
        now = datetime.now(UTC)
        if day > now.date():
            raise ValueError("Le briefing ne peut pas être daté dans le futur.")
        start = datetime.combine(day, time.min, UTC)
        end = min(start + timedelta(days=1) - timedelta(microseconds=1), now)
        if portfolio_id and await self.session.get(PaperPortfolio, portfolio_id) is None:
            raise LookupError("Simulation introuvable.")
        if held_only and not portfolio_id:
            raise ValueError("Choisissez une simulation pour filtrer les positions détenues.")
        instruments = (await self.session.execute(select(MarketInstrument).order_by(MarketInstrument.id).limit(501))).scalars().all()
        instrument_limit_hit = len(instruments) > 500
        holdings = set((await self.session.execute(select(PaperPosition.instrument_id).where(
            PaperPosition.portfolio_id == portfolio_id, PaperPosition.quantity > 0))).scalars()) if portfolio_id else set()
        instruments = [i for i in instruments[:500] if not held_only or i.id in holdings]
        by_id = {i.id: i for i in instruments}
        alerts_query = select(WorkspaceAlert).where(WorkspaceAlert.created_at >= start, WorkspaceAlert.created_at < end)
        if held_only:
            alerts_query = alerts_query.where(WorkspaceAlert.instrument_id.in_(by_id))
        alerts = (await self.session.execute(alerts_query.order_by(WorkspaceAlert.created_at.desc(), WorkspaceAlert.id).limit(1001))).scalars().all()
        valid = []
        for row in alerts[:1000]:
            published = row.data.get("published_at")
            if published and datetime.fromisoformat(published) > end:
                continue
            valid.append({"id": row.id, "instrument_id": row.instrument_id,
                "held": row.instrument_id in holdings, "kind": row.kind, "detected_at": row.created_at, **row.data})
        observations = (await self.session.execute(select(EarningsObservation).where(
            EarningsObservation.instrument_id.in_(by_id), EarningsObservation.observed_at <= end)
            .order_by(EarningsObservation.observed_at.desc(), EarningsObservation.id).limit(5001))).scalars().all()
        grouped = defaultdict(list)
        for row in observations[:5000]:
            grouped[row.instrument_id].append({**row.data, "id": row.id, "provider": row.provider, "observed_at": row.observed_at.isoformat()})
        upcoming = []
        for identifier, rows in grouped.items():
            if len(observations) > 5000:
                # Missing older reported observations could invalidate a forecast.
                # Do not publish an active-date interpretation from a partial history.
                break
            for item in upcoming_events(rows, end):
                if day <= date.fromisoformat(item["report_date"]) <= day + timedelta(days=14):
                    i = by_id[identifier]
                    upcoming.append({"instrument_id": identifier, "symbol": i.symbol, "exchange": i.exchange,
                        "held": identifier in holdings, **item})
        ciks = {i.cik for i in instruments if i.cik}
        financials = (await self.session.execute(select(FinancialFact).where(FinancialFact.cik.in_(ciks),
            FinancialFact.observed_at >= start, FinancialFact.observed_at < end).order_by(FinancialFact.observed_at.desc(), FinancialFact.id).limit(101))).scalars().all()
        journal = await JournalService(self.session).listing(portfolio_id=portfolio_id, limit=100, as_of=end)
        reviews = [r for r in journal["items"] if r["latest"]["status"] not in {"closed", "invalidated"}
            and date.fromisoformat(r["latest"]["review_on"]) <= day
            and (not held_only or r["instrument_id"] in holdings)]
        counts = Counter(a["instrument_id"] for a in valid if a["instrument_id"] in by_id and a["kind"] != "collection_error")
        # Current holdings are deliberately not reconstructed for past briefings.
        return {"day": day, "generated_at": now, "as_of": end, "items": valid[offset:offset + limit], "total": len(valid),
            "counts": dict(Counter(a["kind"] for a in valid)),
            "research": [{"instrument_id": i, "symbol": by_id[i].symbol, "observations": n, "held": i in holdings}
                for i, n in counts.most_common(20)],
            "upcoming": sorted(upcoming, key=lambda r: (r["report_date"], r["symbol"]))[:50],
            "financials": [{"id": f.id, "cik": f.cik, "observed_at": f.observed_at, **f.data} for f in financials[:100]],
            "reviews": reviews, "limited": instrument_limit_hit or len(alerts) > 1000 or len(observations) > 5000 or len(financials) > 100 or journal["total"] > 100,
            "holdings_notice": "Positions actuellement détenues, pas composition historique du portefeuille. Le filtre historique ne reconstitue pas les anciennes détentions.",
            "notice": "Journée UTC, observations détectées et conservées ; publication distincte de collecte. Liste de lecture sans signal d’achat ni importance déduite. Couverture : 500 titres, 1 000 alertes, 5 000 observations calendrier, 100 mesures et dossiers. Échéances prévisionnelles sur 14 jours, à confirmer."}
