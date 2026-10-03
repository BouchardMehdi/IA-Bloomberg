"""Read-only, explainable research priority; never a return or purchase score."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import Text, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONPATH
from sqlalchemy.orm import load_only, selectinload

from app.core.config import get_settings
from app.market.wls import eligibility
from app.models.analysis_run import AnalysisRun
from app.models.article import Article
from app.models.company import Company, EventCompany
from app.models.entity_registry import EntityRegistry
from app.models.event import Event, EventArticle
from app.models.market import MarketInstrument
from app.services.instrument_research import research_card
from app.services.market_data import MarketDataService
from app.services.usd_valuation import UsdValuationService

WINDOW_DAYS = 30
MAX_EVENTS = 2000
METHOD_VERSION = "research-priority-v1"
TYPE_POINTS = {"financial_results": 25, "corporate_action": 25, "enforcement": 25, "regulation": 15}
TYPE_CHECKS = {
    "financial_results": "Comparer résultats, marges, trésorerie et perspectives aux attentes.",
    "corporate_action": "Vérifier prix, financement, dilution éventuelle, "
    "conditions et calendrier de l’opération.",
    "enforcement": "Vérifier la portée de la procédure, les coûts possibles, recours et échéances.",
    "regulation": "Vérifier le périmètre de la règle, ses délais et l’exposition de l’émetteur.",
}


def recent_card(event, instrument, now: datetime) -> dict | None:
    card = research_card(event, instrument)
    if card is None:
        return None
    sources = [s for s in card["sources"] if s["published_at"] <= now]
    if not sources:
        return None
    # A later linked source must not make an old announcement look recent.
    primary = [s for s in sources if s["primary"]]
    date_reference = min(primary or sources, key=lambda s: s["published_at"])
    published_at = date_reference["published_at"]
    if published_at < now - timedelta(days=WINDOW_DAYS):
        return None
    return {
        **card,
        "sources": sources,
        "published_at": published_at,
        "publication_id": event.parent_event_id or event.id,
        "date_reference": date_reference,
    }


def recency_points(card: dict, now: datetime) -> int:
    age = now - card["published_at"]
    return 30 if age <= timedelta(days=2) else 20 if age <= timedelta(days=7) else 10


def score_research(cards: list[dict], now: datetime) -> dict:
    # Documentary source_subject links never establish a role in a fact.
    facts = [
        c
        for c in cards
        if c["kind"] == "extracted_fact"
        and c["evidence"]
        and c["evidence"].strip()
        and c["relationship"]["role"] in {"subject", "counterparty", "mention"}
        and c["relationship"]["basis"] in {"security_mention", "issuer_mention"}
        and c.get("publication_group_verified", True)
    ]
    groups = {}

    def key(card):
        specificity = 30 if card["relationship"]["basis"] == "security_mention" else 15
        return (
            recency_points(card, now) + specificity + TYPE_POINTS.get(card["event_type"], 5),
            card["published_at"],
            str(card["event_id"]),
        )

    for card in facts:
        publication = str(card["publication_id"])
        if publication not in groups or key(card) > key(groups[publication]):
            groups[publication] = card
    selected = sorted(groups.values(), key=key, reverse=True)[:3]
    newest = max((c["published_at"] for c in cards), default=None)
    if selected:
        recent = max(recency_points(c, now) for c in selected)
        specific = max(
            30 if c["relationship"]["basis"] == "security_mention" else 15 for c in selected
        )
        category = max(TYPE_POINTS.get(c["event_type"], 5) for c in selected)
    else:
        recent = specific = category = 0
    components = [
        {
            "code": "recency",
            "label": "Récence du fait",
            "points": recent,
            "maximum": 30,
            "event_ids": [c["event_id"] for c in selected if recency_points(c, now) == recent],
        },
        {
            "code": "relationship",
            "label": "Précision du lien avec le titre",
            "points": specific,
            "maximum": 30,
            "event_ids": [
                c["event_id"]
                for c in selected
                if (30 if c["relationship"]["basis"] == "security_mention" else 15) == specific
            ],
        },
        {
            "code": "event_type",
            "label": "Type du fait déclaré, à contrôler",
            "points": category,
            "maximum": 25,
            "event_ids": [
                c["event_id"] for c in selected if TYPE_POINTS.get(c["event_type"], 5) == category
            ],
        },
        {
            "code": "publications",
            "label": "Publications distinctes retenues",
            "points": 5 * len(selected),
            "maximum": 15,
            "event_ids": [c["event_id"] for c in selected],
        },
    ]
    checks = [
        "Vérifier dans les sources le rôle de l’émetteur et la classe d’action concernée.",
        "Comparer aux attentes du marché ; la nouvelle peut déjà être intégrée au cours.",
    ]
    for card in selected:
        question = TYPE_CHECKS.get(card["event_type"])
        if question and question not in checks:
            checks.append(question)
    partial = any(
        c["coverage"]
        and (
            c["coverage"].get("document_truncated")
            or c["coverage"].get("coverage_ratio", 0) < 1
            or c["coverage"].get("analyzed_count", 0) < c["coverage"].get("selected_count", 0)
        )
        for c in selected
    )
    if partial:
        checks.append("Extraction partielle ou document tronqué : consulter le document complet.")
    if selected and any(c["coverage"] is None for c in selected):
        checks.append("Couverture d’extraction non documentée pour au moins un fait retenu.")
    if any(not c.get("publication_group_verified", True) for c in cards):
        checks.append(
            "Regroupement de publication incomplet : certains faits ne contribuent pas au score."
        )
    return {
        "score": sum(c["points"] for c in components),
        "components": components,
        "facts": selected,
        "recent_fact_count": len(facts),
        "recent_publication_count": len({str(c["publication_id"]) for c in cards}),
        "scored_publication_count": len(selected),
        "latest_publication_at": newest,
        "checks": checks,
        "research_status": "facts_to_review"
        if selected
        else "documents_only"
        if cards
        else "no_recent_evidence",
    }


def data_checks(instrument, price, valuation: dict, wls: dict, now: datetime) -> list[dict]:
    today = now.date()
    price_current = (
        price is not None
        and 0 <= (today - price.session_date).days <= get_settings().market_max_price_age_days
    )
    checks = [
        {
            "code": "price",
            "status": "available" if price_current else "stale" if price else "missing",
            "message": "Clôture locale récente"
            if price_current
            else "Clôture ancienne ou future"
            if price
            else "Clôture locale manquante",
            "source_url": price.source_url if price else None,
            "as_of": price.session_date if price else None,
        }
    ]
    conversion = valuation.get("conversion")
    if instrument.currency == "USD":
        fx_status, fx_message = "not_required", "Conversion FX non nécessaire pour USD"
    elif price is None:
        fx_status, fx_message = "not_evaluated", "Taux à vérifier une fois la date du cours connue"
    elif conversion is None:
        fx_status, fx_message = "missing", "Taux daté au plus tard à la séance manquant"
    else:
        fx_date = datetime.fromisoformat(conversion["fx_date"]).date()
        current = 0 <= (today - fx_date).days <= get_settings().market_max_fx_age_days
        fx_status, fx_message = (
            ("available", "Taux de conversion récent")
            if current
            else ("stale", "Taux de conversion ancien ou futur")
        )
    checks.append(
        {
            "code": "fx",
            "status": fx_status,
            "message": fx_message,
            "source_url": conversion.get("fx_source_url") if conversion else None,
            "as_of": conversion.get("fx_date") if conversion else None,
        }
    )
    checks.append(
        {
            "code": "wls",
            "status": wls["status"],
            "message": "Présent dans l’export WLS importé"
            if wls["status"] == "verified"
            else "Éligibilité WLS non vérifiée",
            "source_url": wls["source_url"],
            "as_of": wls["as_of"],
        }
    )
    if valuation["status"] == "invalid_conversion":
        checks.append(
            {
                "code": "conversion",
                "status": "invalid",
                "message": "Conversion USD non représentable",
                "source_url": None,
                "as_of": None,
            }
        )
    return checks


class ResearchRankingService:
    def __init__(self, session):
        self.session = session

    async def ranking(self, limit: int = 20, offset: int = 0) -> dict:
        now = datetime.now(UTC)
        instruments = (await self.session.execute(select(MarketInstrument))).scalars().all()
        by_cik = defaultdict(list)
        for instrument in instruments:
            if instrument.cik:
                by_cik[instrument.cik].append(instrument)
        cards = defaultdict(list)
        examined, limited = 0, False
        if by_cik:
            ciks = list(by_cik)
            recent_sources = (
                select(EventArticle.event_id)
                .join(Article, Article.id == EventArticle.article_id)
                .where(
                    Article.published_at >= now - timedelta(days=WINDOW_DAYS),
                    Article.published_at <= now,
                )
            )
            issuer = (
                select(EventCompany.event_id)
                .join(Company, Company.id == EventCompany.company_id)
                .where(Company.cik.in_(ciks))
            )
            resolved_ciks = func.jsonb_path_query_array(
                Event.structured_data,
                literal(
                    '$.entity_resolution.entities[*] ? (@.status == "resolved").candidates[*].cik',
                    type_=JSONPATH,
                ),
            )
            published_at = (
                select(func.min(Article.published_at))
                .select_from(EventArticle)
                .join(Article, Article.id == EventArticle.article_id)
                .where(EventArticle.event_id == Event.id, Article.published_at <= now)
                .correlate(Event)
                .scalar_subquery()
            )
            query = (
                select(Event)
                .where(
                    Event.merged_into_event_id.is_(None),
                    Event.id.in_(recent_sources),
                    or_(Event.id.in_(issuer), resolved_ciks.op("?|")(cast(ciks, ARRAY(Text)))),
                )
                .options(
                    load_only(
                        Event.id,
                        Event.parent_event_id,
                        Event.title,
                        Event.event_type,
                        Event.structured_data,
                        Event.evidence_excerpt,
                        Event.fact_analysis_run_id,
                    ),
                    selectinload(Event.company_links)
                    .selectinload(EventCompany.company)
                    .load_only(Company.cik),
                    selectinload(Event.article_links)
                    .selectinload(EventArticle.article)
                    .load_only(Article.url, Article.document_url, Article.published_at),
                    selectinload(Event.fact_analysis_run).load_only(AnalysisRun.coverage),
                )
                .order_by(published_at.desc().nulls_last(), Event.id)
                .limit(MAX_EVENTS + 1)
            )
            events = (await self.session.execute(query)).scalars().all()
            limited, examined = len(events) > MAX_EVENTS, min(len(events), MAX_EVENTS)
            # Group children of already merged publications for scoring only. Facts stay distinct.
            parent_ids = {
                event.parent_event_id for event in events[:MAX_EVENTS] if event.parent_event_id
            }
            roots = {}
            publication_dates = {}
            if parent_ids:
                lineage = (
                    select(
                        Event.id.label("origin"),
                        Event.id.label("node"),
                        Event.merged_into_event_id.label("target"),
                        literal(0).label("depth"),
                    )
                    .where(Event.id.in_(parent_ids))
                    .cte("publication_lineage", recursive=True)
                )
                lineage = lineage.union_all(
                    select(
                        lineage.c.origin, Event.id, Event.merged_into_event_id, lineage.c.depth + 1
                    )
                    .join(lineage, Event.id == lineage.c.target)
                    .where(lineage.c.depth < 20)
                )
                roots = dict(
                    (
                        await self.session.execute(
                            select(lineage.c.origin, lineage.c.node).where(
                                lineage.c.target.is_(None)
                            )
                        )
                    ).all()
                )
                dated_sources = (
                    await self.session.execute(
                        select(
                            EventArticle.event_id,
                            Article.document_url,
                            Article.url,
                            Article.published_at,
                            EventArticle.is_primary_source,
                        )
                        .join(Article, Article.id == EventArticle.article_id)
                        .where(
                            EventArticle.event_id.in_(set(roots.values())),
                            Article.published_at <= now,
                        )
                    )
                ).all()
                grouped_sources = defaultdict(list)
                for publication_id, document_url, url, date, primary in dated_sources:
                    grouped_sources[publication_id].append(
                        {"url": document_url or url, "published_at": date, "primary": primary}
                    )
                for publication_id, sources in grouped_sources.items():
                    primary = [source for source in sources if source["primary"]]
                    publication_dates[publication_id] = min(
                        primary or sources, key=lambda source: source["published_at"]
                    )
            for event in events[:MAX_EVENTS]:
                related = {link.company.cik for link in event.company_links}
                for entity in (
                    (event.structured_data or {}).get("entity_resolution", {}).get("entities", [])
                ):
                    if entity.get("status") == "resolved":
                        related.update(c.get("cik") for c in entity.get("candidates", []))
                for cik in related:
                    for instrument in by_cik.get(cik, []):
                        card = recent_card(event, instrument, now)
                        if card:
                            if event.parent_event_id:
                                card["publication_group_verified"] = event.parent_event_id in roots
                                card["publication_id"] = roots.get(
                                    event.parent_event_id, event.parent_event_id
                                )
                                reference = publication_dates.get(card["publication_id"])
                                if reference and reference["published_at"] < card["published_at"]:
                                    card["date_reference"] = reference
                                    card["published_at"] = reference["published_at"]
                                if card["published_at"] < now - timedelta(days=WINDOW_DAYS):
                                    continue
                            cards[instrument.id].append(card)
        rows = [
            {"instrument": instrument, **score_research(cards[instrument.id], now)}
            for instrument in instruments
        ]
        rows.sort(
            key=lambda r: (
                -r["score"],
                -(r["latest_publication_at"].timestamp() if r["latest_publication_at"] else 0),
                r["instrument"].symbol,
                r["instrument"].exchange,
                str(r["instrument"].id),
            )
        )
        universe = await self.session.get(EntityRegistry, "wls_universe")
        market = MarketDataService(self.session)
        items = []
        for rank, row in enumerate(rows[offset : offset + limit], start=offset + 1):
            instrument = row.pop("instrument")
            price = await market.latest_price(instrument.id)
            valuation = await UsdValuationService(self.session).quote(
                instrument, price, today=now.date()
            )
            wls = eligibility(instrument, universe)
            if not instrument.cik:
                row["checks"].append(
                    "CIK non fourni : couverture documentaire de cet émetteur indisponible ici ; "
                    "sources internationales à connecter."
                )
            items.append(
                {
                    **row,
                    "rank": rank,
                    "instrument": {
                        "id": instrument.id,
                        "symbol": instrument.symbol,
                        "exchange": instrument.exchange,
                        "name": instrument.name,
                        "currency": instrument.currency,
                        "quote_multiplier": instrument.quote_multiplier,
                        "registry_url": instrument.registry_url,
                        "identity_as_of": instrument.identity_as_of,
                        "registry_observed_at": instrument.registry_observed_at,
                    },
                    "data_checks": data_checks(instrument, price, valuation, wls, now),
                    "usd_valuation": valuation,
                    "wls_eligibility": wls,
                }
            )
        return {
            "items": items,
            "total_tracked": len(rows),
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "as_of": now,
            "window_days": WINDOW_DAYS,
            "method_version": METHOD_VERSION,
            "coverage": {
                "events_examined": examined,
                "event_limit": MAX_EVENTS,
                "limited": limited,
            },
            "notice": "Priorité de recherche sur les titres suivis, "
            "pas score de rentabilité ni signal d’achat. "
            "L’absence de fait rapproché ne prouve pas l’absence de nouvelles.",
        }
