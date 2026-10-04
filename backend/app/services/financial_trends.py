"""Compare issuer observations in the same filing and on equal durations only."""

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy import select

from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument

MAX_OBSERVATIONS = 2000


def snapshot(rows):
    row = rows[0]
    return {
        "value": row["value"] if len({Decimal(r["value"]) for r in rows}) == 1 else None,
        "start": row["start"],
        "end": row["end"],
        "sources": [
            {
                "id": item["id"],
                "url": item["source_url"],
                "filed": item["filed"],
                "accession": item["accession"],
                "value": item["value"],
            }
            for item in rows
        ],
    }


def compare_results(items: list[dict], now: datetime) -> list[dict]:
    groups = defaultdict(list)
    for row in items:
        if (
            row["metric"] in {"revenue", "net_income"}
            and row.get("start")
            and row.get("taxonomy") == "us-gaap"
            and date.fromisoformat(row["end"]) <= now.date()
            and date.fromisoformat(row["filed"]) <= now.date()
        ):
            groups[(row["metric"], row["concept"], row["unit"])].append(row)
    comparisons = []
    for (metric, concept, unit), rows in sorted(groups.items()):
        latest_end = max(row["end"] for row in rows)
        starts = sorted({row["start"] for row in rows if row["end"] == latest_end})
        for start in starts:
            current = [row for row in rows if row["start"] == start and row["end"] == latest_end]
            filed = max(row["filed"] for row in current)
            current = [row for row in current if row["filed"] == filed]
            output = {
                "metric": metric,
                "concept": concept,
                "unit": unit,
                "status": "not_comparable",
                "current": snapshot(current),
                "previous": None,
                "delta": None,
                "percent": None,
                "reason": None,
                "direction": None,
            }
            comparisons.append(output)
            if len({Decimal(row["value"]) for row in current}) != 1:
                output["reason"] = (
                    "Valeurs actuelles contradictoires dans les dépôts les plus récents."
                )
                continue
            previous = []
            complete = True
            for accession in {row["accession"] for row in current}:
                matches = [
                    row
                    for row in rows
                    if row["accession"] == accession
                    and row["filed"] == filed
                    and date.fromisoformat(row["end"]) < date.fromisoformat(start)
                    and 350
                    <= (date.fromisoformat(start) - date.fromisoformat(row["start"])).days
                    <= 378
                    and (date.fromisoformat(start) - date.fromisoformat(row["start"])).days
                    == (date.fromisoformat(latest_end) - date.fromisoformat(row["end"])).days
                ]
                complete = complete and bool(matches)
                previous.extend(matches)
            if not complete:
                output["reason"] = "Période précédente de même durée absente du même dépôt."
                continue
            contexts = {(row["start"], row["end"], Decimal(row["value"])) for row in previous}
            if len(contexts) != 1:
                output["reason"] = "Périodes ou valeurs précédentes ambiguës ; calcul bloqué."
                continue
            output["previous"] = snapshot(previous)
            before, after = Decimal(previous[0]["value"]), Decimal(current[0]["value"])
            with localcontext() as context:
                context.prec = 50
                output["delta"] = str(after - before)
                if before > 0:
                    output["percent"] = str(
                        ((after - before) / before * 100).quantize(Decimal("0.01"))
                    )
            output["status"] = "comparable"
            output["reason"] = (
                "Même concept US-GAAP, unité, durée exacte et dépôt ; "
                "décalage annuel de 350 à 378 jours. Variation publiée, "
                "sans correction de périmètre ni prévision de rendement."
            )
            if before <= 0:
                output["reason"] += " Pourcentage non calculé : base nulle ou négative."
            output["direction"] = (
                "turned_profitable"
                if before < 0 < after
                else "turned_loss"
                if after < 0 < before
                else "increase"
                if after > before
                else "decrease"
                if after < before
                else "unchanged"
            )
    return comparisons


class FinancialTrendsService:
    def __init__(self, session):
        self.session = session

    async def detail(self, instrument_id: UUID):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        now = datetime.now(UTC)
        rows = (
            (
                await self.session.execute(
                    select(FinancialFact)
                    .where(
                        FinancialFact.cik == instrument.cik,
                        FinancialFact.data["metric"].astext.in_(["revenue", "net_income"]),
                    )
                    .order_by(
                        FinancialFact.period_end.desc(),
                        FinancialFact.filed_on.desc(),
                        FinancialFact.id,
                    )
                    .limit(MAX_OBSERVATIONS + 1)
                )
            )
            .scalars()
            .all()
            if instrument.cik
            else []
        )
        limited = len(rows) > MAX_OBSERVATIONS
        items = [{**row.data, "id": row.id} for row in rows[:MAX_OBSERVATIONS]]
        return {
            "items": [] if limited else compare_results(items, now),
            "generated_at": now,
            "coverage": {"limited": limited, "examined": len(items), "limit": MAX_OBSERVATIONS},
            "notice": "Évolution annuelle des observations de l’émetteur, sans appel IA. "
            "Les durées restent explicites : un cumul n’est pas un trimestre. "
            "Une comparaison comptable ne prouve ni croissance organique ni opportunité d’achat.",
            "reason": "Couverture bornée : calculs bloqués pour éviter une sélection incomplète."
            if limited
            else None,
        }
