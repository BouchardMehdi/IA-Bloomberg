from collections import Counter
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument
from app.services.financial_results import FinancialResultsService
from app.services.market_data import MarketDataService
from app.services.valuation import ValuationService


class MarketCoverageService:
    def __init__(self, session):
        self.session = session

    async def detail(self):
        market = await MarketDataService(self.session).list_instruments()
        counters = Counter()
        items = []
        for row in market["items"]:
            valuation = await ValuationService(self.session).detail(row["id"])
            instrument = await self.session.get(MarketInstrument, row["id"])
            run = (
                await FinancialResultsService(self.session).latest(instrument.cik)
                if instrument.cik
                else None
            )
            fact_count = (
                (
                    await self.session.execute(
                        select(func.count())
                        .select_from(FinancialFact)
                        .where(FinancialFact.cik == instrument.cik)
                    )
                ).scalar_one()
                if instrument.cik
                else 0
            )
            missing = []
            if row["usd_valuation"]["status"] != "available":
                missing.append(row["usd_valuation"]["status"])
            if row["wls_eligibility"]["status"] != "verified":
                missing.append("wls_unverified")
            if row["wls_preparation"]["status"] != "matched":
                missing.append("listing_unresolved")
            if row["price_provider"] == "manual":
                missing.append("price_mapping_missing")
            if valuation["calculation"]["status"] != "available":
                missing.append("valuation_blocked")
            if not valuation["observation"] or not valuation["observation"].get("reference"):
                missing.append("valuation_reference_missing")
            if not run or run.status != "success" or not fact_count:
                missing.append("financials_unavailable")
            if row["error_code"]:
                missing.append("price_collection_error")
            counters.update(missing)
            items.append(
                {
                    "instrument_id": row["id"],
                    "symbol": row["symbol"],
                    "exchange": row["exchange"],
                    "name": row["name"],
                    "currency": row["currency"],
                    "missing": missing,
                    "price": row["latest_price"],
                    "usd_status": row["usd_valuation"]["status"],
                    "valuation": valuation["calculation"],
                    "financial_collection": {
                        "fact_count": fact_count,
                        "status": run.status
                        if run
                        else "unsupported"
                        if not instrument.cik
                        else "pending",
                        "started_at": run.started_at if run else None,
                    },
                    "collection_error": row["error_code"],
                    "retry_at": row["retry_at"],
                }
            )
        return {
            "observed_at": datetime.now(UTC),
            "watched_count": len(items),
            "counts": dict(counters),
            "items": items,
            "price_collection": await MarketDataService(self.session).collection_status(),
            "notice": "Couverture des seuls titres suivis, pas de tout le WLS. "
            "Données absentes et blocages ne constituent pas un avis d’investissement.",
        }

    async def valuation_preparation(self, instrument_id):
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        candidates = []
        if instrument.cik:
            # Documentary candidates only. No automatic assignment to a security or session.
            rows = (
                (
                    await self.session.execute(
                        select(FinancialFact)
                        .where(
                            FinancialFact.cik == instrument.cik,
                            FinancialFact.data["metric"].astext == "eps_diluted",
                        )
                        .order_by(FinancialFact.filed_on.desc(), FinancialFact.id)
                        .limit(100)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                start, end = row.data.get("start"), row.data.get("end")
                if (
                    start
                    and end
                    and 350 <= (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 <= 378
                ):
                    candidates.append({"id": row.id, "observed_at": row.observed_at, **row.data})
        return {
            "instrument_id": instrument_id,
            "issuer_candidates": candidates[:10],
            "search_limit": 100,
            "candidates_limited": len(candidates) > 10,
            "valuation": await ValuationService(self.session).detail(instrument_id),
            "required": [
                "BPA annuel GAAP dilué par titre exact",
                "Preuve couvrant la séance et les splits/ADR/classes",
                "Devise, période annuelle, URLs et dates de publication",
                "Référence comparable sourcée pour qualifier le multiple",
            ],
            "notice": "Les candidats SEC concernent l’émetteur. Ils ne sont ni attribués "
            "à cette cotation, ni injectés dans un PER. Importer uniquement des preuves "
            "complètes explicitement documentées ; aucun trimestre annualisé.",
        }
