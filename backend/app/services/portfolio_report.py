from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.market import MarketInstrument
from app.models.workspace import BenchmarkPoint, InstrumentProfile
from app.services.paper_portfolio import PaperPortfolioService
from app.services.portfolio_history import PortfolioHistoryService


def fingerprint(data):
    import hashlib
    import json
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def allocation(snapshot, profiles):
    total = snapshot["total_value"]
    usable = total is not None and total > 0 and not snapshot["valuation_stale"]
    groups = {key: defaultdict(lambda: {"value_usd": Decimal(0), "unpriced": 0, "titles": 0})
              for key in ("sector", "country", "currency", "security")}
    for p in snapshot["positions"]:
        profile = profiles.get(str(p["instrument_id"]), {})
        labels = {"sector": profile.get("sector") or "Non documenté",
                  "country": profile.get("country") or "Non documenté", "currency": p["currency"],
                  "security": f"{p['symbol']} · {p['exchange']}"}
        for key, label in labels.items():
            item = groups[key][label]
            item["titles"] += 1
            if p["value"] is None:
                item["unpriced"] += 1
            else:
                item["value_usd"] += Decimal(p["value"])
    result = {}
    for key, values in groups.items():
        result[key] = [{"label": label, **item,
                       "value_usd": None if item["unpriced"] else item["value_usd"],
                       "weight_pct": (item["value_usd"] / total * 100).quantize(Decimal(".01")) if usable else None}
                      for label, item in sorted(values.items())]
    result["cash"] = {"value_usd": snapshot["cash"],
                      "weight_pct": (snapshot["cash"] / total * 100).quantize(Decimal(".01")) if usable else None}
    result["status"] = "available" if usable else "incomplete_or_stale"
    return result


def benchmark_comparison(history, points):
    if len(history) < 2:
        return {"status": "unavailable", "reason": "Deux journées réellement observées sont nécessaires."}
    first, last = history[0], history[-1]
    if any(p["status"] != "available" or p["total_value"] is None for p in (first, last)):
        return {"status": "unavailable", "reason": "Valorisation absente ou ancienne à une borne de la période."}
    by_date = {str(p.session_date): p for p in points}
    a, b = by_date.get(str(first["date"])), by_date.get(str(last["date"]))
    if not a or not b:
        return {"status": "unavailable", "reason": "Valeurs d’indice manquantes aux mêmes dates UTC. Aucune interpolation."}
    if Decimal(first["total_value"]) <= 0:
        return {"status": "unavailable", "reason": "Valeur initiale non positive."}
    portfolio_return = (Decimal(last["total_value"]) / Decimal(first["total_value"]) - 1) * 100
    benchmark_return = (Decimal(b.data["level"]) / Decimal(a.data["level"]) - 1) * 100
    return {"status": "available", "starts_on": first["date"], "ends_on": last["date"],
            "portfolio_pct": portfolio_return.quantize(Decimal(".01")),
            "benchmark_pct": benchmark_return.quantize(Decimal(".01")),
            "difference_pp": (portfolio_return - benchmark_return).quantize(Decimal(".01"))
                if a.data["convention"] != "price" else None,
            "convention": a.data["convention"], "sources": [a.data, b.data],
            "observed_days": len(history),
            "notice": "Instantanés du portefeuille et niveaux d’indice déclarés aux mêmes dates, sans garantie de même heure de clôture. Les impôts, frais, dividendes omis et conventions peuvent différer. Aucun rendement officiel Bloomberg certifié."}


class PortfolioReportService:
    def __init__(self, session):
        self.session = session

    async def add_profile(self, instrument_id, request):
        if await self.session.get(MarketInstrument, instrument_id) is None:
            raise LookupError("Titre introuvable.")
        data = request.model_dump(mode="json")
        identifier = (await self.session.execute(insert(InstrumentProfile).values(
            instrument_id=instrument_id, fingerprint=fingerprint(data), data=data,
            observed_at=datetime.now(UTC),
        ).on_conflict_do_nothing().returning(InstrumentProfile.id))).scalar_one_or_none()
        await self.session.commit()
        return {"inserted": identifier is not None}

    async def add_benchmark(self, request):
        data = request.model_dump(mode="json")
        # Series conventions never silently change across imported dates.
        from sqlalchemy import func
        await self.session.execute(select(func.pg_advisory_xact_lock(721932)))
        sample = (await self.session.execute(select(BenchmarkPoint).where(
            BenchmarkPoint.series == request.series).limit(1))).scalar_one_or_none()
        if sample and any(sample.data[k] != data[k] for k in ("name", "currency", "convention")):
            raise ValueError("Conventions différentes : utiliser une autre série.")
        existing = (await self.session.execute(select(BenchmarkPoint).where(
            BenchmarkPoint.series == request.series, BenchmarkPoint.session_date == str(request.session_date)))).scalar_one_or_none()
        if existing and existing.data != data:
            raise ValueError("Cette séance possède déjà une observation différente. Aucun écrasement.")
        if not existing:
            self.session.add(BenchmarkPoint(series=request.series, session_date=str(request.session_date), data=data))
        await self.session.commit()
        return {"inserted": existing is None}

    async def detail(self, portfolio_id, series=None):
        snapshot = await PaperPortfolioService(self.session).snapshot(portfolio_id)
        if snapshot is None:
            raise LookupError("Portefeuille introuvable.")
        ids = [p["instrument_id"] for p in snapshot["positions"]]
        rows = (await self.session.execute(select(InstrumentProfile).where(
            InstrumentProfile.instrument_id.in_(ids)).order_by(
                InstrumentProfile.instrument_id, InstrumentProfile.observed_at.desc(), InstrumentProfile.id.desc())
            .distinct(InstrumentProfile.instrument_id))).scalars().all()
        profiles = {str(r.instrument_id): r.data for r in rows}
        history = await PortfolioHistoryService(self.session).detail(portfolio_id, 1000)
        points = (await self.session.execute(select(BenchmarkPoint).where(BenchmarkPoint.series == series))).scalars().all() if series else []
        series_rows = (await self.session.execute(select(BenchmarkPoint.series, BenchmarkPoint.data["name"].astext)
                       .distinct())).all()
        return {"allocation": allocation(snapshot, profiles), "profiles": profiles,
                "benchmark_series": [{"id": a, "name": b} for a, b in series_rows],
                "comparison": benchmark_comparison(history["items"], points),
                "history_limited": history["limited"],
                "notice": "Poids sur la valeur totale en USD, liquidités comprises. Pays et secteur déclarés par source ; aucune déduction à partir du ticker ou du lieu de cotation. Les poids sont bloqués si la valorisation est incomplète ou ancienne."}
