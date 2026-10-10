from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.market import MarketInstrument
from app.models.workspace import DataProposal
from app.services.earnings import EarningsService
from app.services.international_market import InternationalMarketService
from app.services.portfolio_actions import PortfolioActionService
from app.services.portfolio_report import fingerprint
from app.services.valuation import ValuationService


class DataImportService:
    def __init__(self, session):
        self.session = session

    async def ingest(self, request):
        results = []
        for index, row in enumerate(request.items):
            try:
                if row.kind != "fx" and await self.session.get(MarketInstrument, row.instrument_id) is None:
                    raise ValueError("Titre introuvable.")
                if row.kind == "earnings":
                    result = await EarningsService(self.session).add(row.instrument_id, row.observation)
                elif row.kind == "valuation":
                    result = await ValuationService(self.session).add(row.instrument_id, row.observation)
                elif row.kind == "price":
                    result = await InternationalMarketService(self.session).save_price(row.instrument_id, row.observation)
                elif row.kind == "fx":
                    result = await InternationalMarketService(self.session).save_fx(row.observation)
                else:
                    data = row.observation.model_dump(mode="json")
                    identifier = (await self.session.execute(insert(DataProposal).values(
                        instrument_id=row.instrument_id, fingerprint=fingerprint(row.model_dump(mode="json")),
                        data=data, observed_at=datetime.now(UTC),
                    ).on_conflict_do_nothing().returning(DataProposal.id))).scalar_one_or_none()
                    await self.session.commit()
                    result = {"inserted": identifier is not None, "proposal": True}
                results.append({"index": index, "status": "accepted", "result": result})
            except (ValueError, LookupError) as exc:
                await self.session.rollback()
                results.append({"index": index, "status": "rejected", "error": str(exc)})
        return {"items": results, "notice": "Données déclarées, sans certification automatique. Les opérations sur titres sont proposées à la validation et ne modifient aucun portefeuille à l’import."}

    async def proposals(self, limit, offset):
        rows = (await self.session.execute(select(DataProposal).order_by(
            DataProposal.observed_at.desc(), DataProposal.id).offset(offset).limit(limit + 1))).scalars().all()
        return {"items": [{"id": r.id, "instrument_id": r.instrument_id, "observed_at": r.observed_at,
                           **r.data} for r in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None}

    async def apply(self, proposal_id, portfolio_id):
        from app.schemas.portfolio_tracking import CorporateActionInput
        proposal = await self.session.get(DataProposal, proposal_id)
        if proposal is None:
            raise LookupError("Proposition introuvable.")
        return await PortfolioActionService(self.session).apply(
            portfolio_id, proposal.instrument_id, CorporateActionInput.model_validate(proposal.data))
