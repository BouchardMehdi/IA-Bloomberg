"""Sourced research dossiers, without sentiment inference or investment scores."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.market.sec_financials import METRIC_LABELS
from app.models.earnings import EarningsObservation
from app.services.financial_results import FinancialResultsService
from app.services.instrument_research import InstrumentResearchService
from app.services.research_ranking import TYPE_CHECKS


def upcoming_events(observations: list[dict], now: datetime) -> list[dict]:
    # Latest observation per provider/kind/period BEFORE filtering dates. A moved
    # or cancelled/past schedule must not resurrect an older future prediction.
    latest = {}
    reported = set()
    for item in observations:
        observed = datetime.fromisoformat(item["observed_at"])
        published = item.get("published_at")
        if observed > now or (published and datetime.fromisoformat(published) > now):
            continue
        period = item["fiscal_period_end"]
        if item["kind"] == "reported":
            reported.add(period)
        key = (item["provider"], item["kind"], period)
        old = latest.get(key)
        if old is None or observed > datetime.fromisoformat(old[0]["observed_at"]):
            latest[key] = [item]
        elif observed == datetime.fromisoformat(old[0]["observed_at"]):
            # Simultaneous conflicting snapshots remain visible.
            old.append(item)
    dates = {}
    candidates = []
    for item in [row for group in latest.values() for row in group]:
        when = date.fromisoformat(item["report_date"])
        period = item["fiscal_period_end"]
        if item["kind"] not in {"schedule", "estimate"} or period in reported:
            continue
        if not now.date() <= when <= now.date() + timedelta(days=180):
            continue
        dates.setdefault(period, set()).add(item["report_date"])
        candidates.append(item)
    distinct = {}
    for item in candidates:
        key = (
            item["provider"],
            item["fiscal_period_end"],
            item["report_date"],
            item["source_url"],
            item.get("published_at"),
        )
        previous = distinct.get(key)
        if previous is None or item["observed_at"] > previous["observed_at"]:
            distinct[key] = item
    return [
        {
            "label": "Résultats prévisionnels à confirmer",
            "report_date": item["report_date"],
            "fiscal_period_end": item["fiscal_period_end"],
            "source_url": item["source_url"],
            "published_at": item.get("published_at"),
            "observed_at": item["observed_at"],
            "provider": item["provider"],
            "conflicting_dates": len(dates[item["fiscal_period_end"]]) > 1,
        }
        for item in sorted(distinct.values(), key=lambda x: (x["report_date"], str(x["id"])))
    ]


def financial_arguments(items: list[dict], now: datetime) -> tuple[list, list]:
    # All definitions/period starts/filings at the most recent net-income end
    # stay separate. No cumulative subtraction, share attribution or trend claim.
    net = [
        item
        for item in items
        if item["metric"] in {"net_income", "operating_cash_flow"}
        and date.fromisoformat(item["filed"]) <= now.date()
        and date.fromisoformat(item["end"]) <= now.date()
    ]
    ends = {
        metric: max(item["end"] for item in net if item["metric"] == metric)
        for metric in {item["metric"] for item in net}
    }
    favorable, risks = [], []
    for item in net:
        if item["end"] != ends[item["metric"]] or Decimal(item["value"]) == 0:
            continue
        positive = Decimal(item["value"]) > 0
        entry = {
            "id": item.get("id"),
            "label": "Résultat net positif de l’émetteur"
            if positive
            else "Perte nette de l’émetteur",
            "value": item["value"],
            "unit": item["unit"],
            "start": item["start"],
            "end": item["end"],
            "concept": item["concept"],
            "accession": item["accession"],
            "sources": [{"url": item["source_url"], "published_at": item["filed"]}],
            "stale_period": (now.date() - date.fromisoformat(item["end"])).days > 180,
            "notice": "Observation comptable de l’émetteur ; ni croissance, ni "
            "valorisation attractive, ni effet sur ce titre ne sont établis.",
        }
        if item["metric"] == "operating_cash_flow":
            entry["label"] = (
                "Flux de trésorerie d’exploitation positif"
                if positive
                else "Flux de trésorerie d’exploitation négatif"
            )
            entry["notice"] = (
                "Flux sur la période indiquée ; ni trésorerie disponible "
                "à une date, ni flux libre, ni rendement attendu."
            )
        (favorable if positive else risks).append(entry)
    return favorable, risks


def liquidity_observations(items: list[dict], now: datetime) -> list[dict]:
    selected = [
        item
        for item in items
        if item["metric"] not in {"net_income", "revenue", "eps_basic", "eps_diluted"}
        and date.fromisoformat(item["end"]) <= now.date()
        and date.fromisoformat(item["filed"]) <= now.date()
    ]
    ends = {
        metric: max(item["end"] for item in selected if item["metric"] == metric)
        for metric in {item["metric"] for item in selected}
    }
    return [
        {
            **item,
            "label": METRIC_LABELS[item["metric"]],
            "stale_period": (now.date() - date.fromisoformat(item["end"])).days > 180,
        }
        for item in selected
        if item["end"] == ends[item["metric"]]
    ]


class OpportunityService:
    def __init__(self, session):
        self.session = session

    async def detail(self, instrument_id: UUID):
        now = datetime.now(UTC)
        research = await InstrumentResearchService(self.session).detail(instrument_id, 100, 0)
        if research is None:
            return None
        financials = await FinancialResultsService(self.session).detail(instrument_id, 2000, 0)
        # Most recent observed snapshots; coverage is explicit if the bound is hit.
        rows = (
            (
                await self.session.execute(
                    select(EarningsObservation)
                    .where(EarningsObservation.instrument_id == instrument_id)
                    .order_by(EarningsObservation.observed_at.desc(), EarningsObservation.id)
                    .limit(1001)
                )
            )
            .scalars()
            .all()
        )
        observations = [
            {
                **row.data,
                "id": row.id,
                "provider": row.provider,
                "observed_at": row.observed_at.isoformat(),
            }
            for row in rows[:1000]
        ]
        upcoming = upcoming_events(observations, now)
        favorable, risks = financial_arguments(financials["items"], now)
        checks = []
        for card in research["items"]:
            sources = [s for s in card["sources"] if s["published_at"] <= now]
            if (
                not sources
                or card["kind"] != "extracted_fact"
                or not card["evidence"]
                or not card["evidence"].strip()
                or card["relationship"]["basis"] == "issuer_document"
            ):
                continue
            checks.append(
                {
                    "event_id": card["event_id"],
                    "title": card["title"],
                    "summary": card["summary"],
                    "evidence": card["evidence"],
                    "relationship": card["relationship"],
                    "sources": sources,
                    "label": TYPE_CHECKS.get(card["event_type"], card["checks"][1]),
                    "coverage": card["coverage"],
                }
            )
        instrument = research["instrument"]
        missing = [
            "Valorisation, échéances de dette, liquidité et perspectives "
            "à analyser avant toute décision. Aucun total de dette ou ratio n’est déduit.",
            "Impact sur ce titre et horizon d’investissement non établis.",
            "Comparaison aux attentes : périodes, conventions et antériorité à vérifier.",
            "Frais, dates et limites du challenge restent à confirmer.",
        ]
        if instrument["wls_eligibility"]["status"] != "verified":
            missing.append("Éligibilité WLS non vérifiée : export autorisé attendu.")
        if not instrument["latest_price"] or instrument["latest_price"]["stale"]:
            missing.append("Clôture locale récente indisponible.")
        if instrument["usd_valuation"]["status"] != "available":
            missing.append("Valorisation en USD récente indisponible : contrôler cours et taux.")
        available = set(financials["available_metrics"])
        absent = {
            "revenue",
            "net_income",
            "eps_basic",
            "eps_diluted",
            "cash",
            "operating_cash_flow",
            "capex",
        } - available
        if absent:
            missing.append(
                "Mesures SEC absentes de la couverture : "
                + ", ".join(METRIC_LABELS[metric] for metric in sorted(absent))
            )
        if not available.intersection(
            {
                "short_term_debt",
                "debt_current",
                "debt_noncurrent",
                "long_term_debt",
                "debt_leases_current",
                "debt_leases_noncurrent",
            }
        ):
            missing.append(
                "Aucune mesure d’endettement couverte ; absence ne signifie pas dette nulle."
            )
        if financials["collection"]["status"] != "success":
            missing.append(
                "Collecte financière SEC non réussie : contrôler son état et sa couverture."
            )
        if any(item["conflicting_dates"] for item in upcoming):
            missing.append(
                "Dates de résultats contradictoires : confirmation officielle nécessaire."
            )
        if not upcoming:
            missing.append("Aucune prochaine date exploitable dans le calendrier conservé.")
        if not checks:
            missing.append(
                "Aucun fait extrait avec preuve et mention exploitable dans cette couverture."
            )
        limited = (
            research["next_offset"] is not None
            or financials["next_offset"] is not None
            or len(rows) > 1000
        )
        if limited:
            missing.append(
                "Fiche partielle : borne documentaire, financière ou calendrier atteinte."
            )
        return {
            "instrument": instrument,
            "generated_at": now,
            "favorable": favorable,
            "risks": risks,
            "liquidity": liquidity_observations(financials["items"], now),
            "checks": checks,
            "upcoming": upcoming,
            "missing_data": missing,
            "coverage": {
                "limited": limited,
                "document_candidates_limit": 100,
                "financial_observations_limit": 2000,
                "calendar_limit": 1000,
            },
            "notice": "Fiche d’opportunité à examiner, sans recommandation d’achat "
            "ni score de rendement. Les scores existants priorisent uniquement la recherche. "
            "Une rubrique vide ne prouve pas l’absence de risques ou d’éléments favorables.",
        }
