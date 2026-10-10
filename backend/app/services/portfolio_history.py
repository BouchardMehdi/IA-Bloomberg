import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.portfolio import PaperPortfolio
from app.models.portfolio_tracking import PortfolioObservation


class PortfolioHistoryService:
    def __init__(self, session):
        self.session = session

    async def capture(self, portfolio_id: UUID, *, commit=True):
        from app.services.paper_portfolio import PaperPortfolioService

        portfolio = (
            await self.session.execute(
                select(PaperPortfolio).where(PaperPortfolio.id == portfolio_id).with_for_update()
            )
        ).scalar_one_or_none()
        if portfolio is None:
            raise LookupError("Portefeuille introuvable.")
        now = datetime.now(UTC)
        snapshot = await PaperPortfolioService(self.session).snapshot(portfolio_id)
        status = (
            "missing"
            if snapshot["total_value"] is None
            else "stale"
            if snapshot["valuation_stale"]
            else "available"
        )
        data = jsonable_encoder(
            {
                "status": status,
                "cash": snapshot["cash"],
                "initial_capital": snapshot["initial_capital"],
                "total_value": snapshot["total_value"],
                "total_pnl": snapshot["total_pnl"],
                "return_pct": snapshot["return_pct"],
                "realized_pnl": snapshot["realized_pnl"],
                "dividend_income": snapshot["dividend_income"],
                "wls_policy": snapshot["wls_policy"],
                "positions": snapshot["positions"],
                "latest_trade_ids": [t["id"] for t in snapshot["trades"]],
                "action_ids": snapshot["action_ids"],
            },
            custom_encoder={Decimal: str},
        )
        latest = (
            await self.session.execute(
                select(PortfolioObservation)
                .where(
                    PortfolioObservation.portfolio_id == portfolio_id,
                    PortfolioObservation.observation_date == now.date(),
                )
                .order_by(PortfolioObservation.observed_at.desc(), PortfolioObservation.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest and latest.data == data:
            if commit:
                await self.session.commit()
            return {"id": latest.id, "inserted": False, "observed_at": latest.observed_at}
        # Hash chain permits A -> B -> A within a day without losing the last state.
        fingerprint = hashlib.sha256(
            json.dumps(
                {"previous": str(latest.id) if latest else None, "data": data}, sort_keys=True
            ).encode()
        ).hexdigest()
        identifier = (
            await self.session.execute(
                insert(PortfolioObservation)
                .values(
                    portfolio_id=portfolio_id,
                    observation_date=now.date(),
                    observed_at=now,
                    fingerprint=fingerprint,
                    data=data,
                )
                .returning(PortfolioObservation.id)
            )
        ).scalar_one()
        if commit:
            await self.session.commit()
        return {"id": identifier, "inserted": True, "observed_at": now}

    async def detail(self, portfolio_id: UUID, limit=365):
        if await self.session.get(PaperPortfolio, portfolio_id) is None:
            return None
        # Last actual observation of each UTC day, never a reconstructed closing NAV.
        rows = (
            (
                await self.session.execute(
                    select(PortfolioObservation)
                    .where(PortfolioObservation.portfolio_id == portfolio_id)
                    .distinct(PortfolioObservation.observation_date)
                    .order_by(
                        PortfolioObservation.observation_date.desc(),
                        PortfolioObservation.observed_at.desc(),
                        PortfolioObservation.id.desc(),
                    )
                    .limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [
                {"id": r.id, "date": r.observation_date, "observed_at": r.observed_at, **r.data}
                for r in reversed(rows[:limit])
            ],
            "limited": len(rows) > limit,
            "timezone": "UTC",
            "notice": "Dernier instantané observé de chaque jour UTC, pas une clôture "
            "synchronisée ni un backtest. Jours absents non reconstitués. Cours et taux "
            "anciens/manquants exclus de la courbe. Dividendes et splits seulement s’ils "
            "ont été enregistrés ; aucune équivalence au rendement officiel WLS.",
        }

    async def collect(self):
        ids = (await self.session.execute(select(PaperPortfolio.id))).scalars().all()
        inserted = 0
        for identifier in ids:
            result = await self.capture(identifier)
            inserted += result["inserted"]
        return {"portfolios": len(ids), "inserted": inserted}
