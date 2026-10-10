from datetime import UTC, datetime

from sqlalchemy import select

from app.market.providers import QuoteIdentity
from app.models.market import MarketInstrument
from app.models.portfolio_tracking import PriceListingMapping


class PriceMappingService:
    def __init__(self, session):
        self.session = session

    async def detail(self):
        rows = (await self.session.execute(select(PriceListingMapping))).scalars().all()
        return {
            "items": [{"observed_at": r.observed_at, **r.data} for r in rows],
            "notice": "Correspondances déclarées par cotation, sans suffixe deviné. "
            "La saisie ne certifie pas les preuves. Quota partagé Alpha Vantage ; "
            "disponibilité des marchés dépend du fournisseur.",
        }

    async def add(self, request):
        instrument = (
            await self.session.execute(
                select(MarketInstrument)
                .where(MarketInstrument.id == request.instrument_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if instrument is None:
            raise LookupError("Titre introuvable.")
        expected = QuoteIdentity.from_instrument(instrument)
        identity = QuoteIdentity.model_validate(
            {k: getattr(request, k) for k in QuoteIdentity.model_fields}
        )
        if identity != expected or instrument.exchange in {"NYSE", "Nasdaq"}:
            raise ValueError("Correspondance internationale exacte requise pour cette cotation.")
        data = request.model_dump(mode="json")
        existing = await self.session.get(PriceListingMapping, instrument.id)
        if existing and existing.data != data:
            raise ValueError(
                "Correspondance déjà enregistrée : remplacement contradictoire refusé."
            )
        if not existing:
            self.session.add(
                PriceListingMapping(
                    instrument_id=instrument.id, observed_at=datetime.now(UTC), data=data
                )
            )
        instrument.price_provider = "alpha_vantage"
        await self.session.commit()
        return {"inserted": existing is None, "instrument_id": instrument.id}
