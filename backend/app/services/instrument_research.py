"""Read-only research: issuer context never establishes a security-specific impact."""

from uuid import UUID

from sqlalchemy import false, or_, select
from sqlalchemy.orm import selectinload

from app.models.company import Company, EventCompany
from app.models.event import Event, EventArticle
from app.services.market_data import MarketDataService


def relationship(event, instrument) -> dict | None:
    if not instrument.cik:
        return None
    entities = (event.structured_data or {}).get("entity_resolution", {}).get("entities", [])
    matches = []
    for entity in entities:
        if entity.get("status") != "resolved" or not entity.get("quote"):
            continue
        candidates = entity.get("candidates", [])
        if len(candidates) != 1 or candidates[0].get("cik") != instrument.cik:
            continue
        candidate = candidates[0]
        security = (
            entity.get("kind") == "equity"
            and candidate.get("ticker") == instrument.symbol
            and candidate.get("exchange") == instrument.exchange
        )
        matches.append(
            {
                "basis": "security_mention" if security else "issuer_mention",
                "role": entity.get("role", "mention"),
                "quote": entity["quote"],
            }
        )
    if matches:
        return next((m for m in matches if m["basis"] == "security_mention"), matches[0])
    if any(link.company.cik == instrument.cik for link in event.company_links):
        return {"basis": "issuer_document", "role": "source_subject", "quote": None}
    return None


def research_card(event, instrument) -> dict | None:
    link = relationship(event, instrument)
    sources = [
        {
            "url": item.article.document_url or item.article.url,
            "published_at": item.article.published_at,
            "primary": item.is_primary_source,
        }
        for item in event.article_links
        if item.article.published_at is not None
    ]
    if link is None or not sources:
        return None
    fact = (event.structured_data or {}).get("fact") if event.parent_event_id else None
    return {
        "event_id": event.id,
        "kind": "extracted_fact" if event.parent_event_id and fact else "publication",
        "title": event.title,
        "summary": fact.get("summary") if fact else None,
        "event_type": event.event_type,
        "relationship": link,
        "evidence": event.evidence_excerpt if fact else None,
        "sources": sources,
        "coverage": event.fact_analysis_run.coverage if event.fact_analysis_run else None,
        "impact": "À déterminer : aucun effet sur le cours n’est établi par cette fiche.",
        "horizon": "À déterminer après examen du calendrier et du document complet.",
        "checks": [
            "Vérifier dans le document le rôle de la société et les titres concernés.",
            "Évaluer le montant, les conditions et le calendrier du fait avant de conclure.",
            "Comparer aux attentes du marché ; une nouvelle peut être déjà intégrée au cours.",
        ],
    }


class InstrumentResearchService:
    def __init__(self, session):
        self.session = session

    async def detail(self, instrument_id: UUID, limit: int, offset: int) -> dict | None:
        from app.models.market import MarketInstrument

        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            return None
        issuer = (
            select(EventCompany.event_id)
            .join(Company, Company.id == EventCompany.company_id)
            .where(Company.cik == instrument.cik)
        )
        resolved = Event.structured_data.contains(
            {
                "entity_resolution": {
                    "entities": [{"status": "resolved", "candidates": [{"cik": instrument.cik}]}]
                }
            }
        )
        if not instrument.cik:
            resolved = false()
        query = (
            select(Event)
            .where(Event.merged_into_event_id.is_(None), or_(Event.id.in_(issuer), resolved))
            .options(
                selectinload(Event.company_links).selectinload(EventCompany.company),
                selectinload(Event.article_links).selectinload(EventArticle.article),
                selectinload(Event.fact_analysis_run),
            )
            .order_by(Event.event_datetime.desc().nulls_last(), Event.created_at.desc(), Event.id)
            .offset(offset)
            .limit(limit + 1)
        )
        events = (await self.session.execute(query)).scalars().all()
        cards = [card for event in events[:limit] if (card := research_card(event, instrument))]
        market = await MarketDataService(self.session).list_instruments(instrument_id)
        return {
            "instrument": next(i for i in market["items"] if i["id"] == instrument_id),
            "items": cards,
            "next_offset": offset + limit if len(events) > limit else None,
            "limit": limit,
            "offset": offset,
            "notice": "Liens documentaires et mentions identifiées, pas recommandations d’achat. "
            "Les rôles extraits et l’analyse partielle doivent être vérifiés.",
        }
