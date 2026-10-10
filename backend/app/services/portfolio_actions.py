from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.market.paper import money
from app.models.market import FxRate, MarketInstrument
from app.models.portfolio import PaperPortfolio, PaperPosition, PaperTrade
from app.models.portfolio_tracking import PortfolioAction
from app.services.market_data import MarketDataService
from app.services.portfolio_history import PortfolioHistoryService


def split_quantity(quantity, numerator, denominator):
    result, remainder = divmod(quantity * numerator, denominator)
    if remainder or result > 2_000_000_000:
        raise ValueError(
            "Split refusé : fraction de titre ou quantité hors capacité. "
            "Aucun paiement compensatoire n’est inventé."
        )
    return result


def entitled_quantity(trades, actions, ex_date):
    entries = [
        (t.executed_at.astimezone(UTC), 1, t.quantity if t.side == "buy" else -t.quantity, None)
        for t in trades
        if t.executed_at.astimezone(UTC).date() < ex_date
    ]
    entries += [
        (datetime.combine(a.effective_date, time.min, UTC), 0, 0, a.data["request"])
        for a in actions
        if a.kind == "split" and a.effective_date < ex_date
    ]
    held = 0
    for _, _, delta, action in sorted(entries, key=lambda e: (e[0], e[1])):
        held = (
            split_quantity(held, action["numerator"], action["denominator"])
            if action
            else held + delta
        )
        if held < 0:
            raise ValueError("Historique des quantités incohérent.")
    return held


class PortfolioActionService:
    def __init__(self, session):
        self.session = session

    async def detail(self, portfolio_id):
        if await self.session.get(PaperPortfolio, portfolio_id) is None:
            return None
        rows = (
            (
                await self.session.execute(
                    select(PortfolioAction)
                    .where(PortfolioAction.portfolio_id == portfolio_id)
                    .order_by(PortfolioAction.observed_at.desc())
                    .limit(201)
                )
            )
            .scalars()
            .all()
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "instrument_id": r.instrument_id,
                    "kind": r.kind,
                    "effective_date": r.effective_date,
                    "observed_at": r.observed_at,
                    **r.data,
                }
                for r in rows[:200]
            ],
            "limited": len(rows) > 200,
            "notice": "Opérations déclarées et sourcées de cette simulation. "
            "Dividendes nets, sans réinvestissement ; règles fiscales et Bloomberg non certifiées.",
        }

    async def apply(self, portfolio_id, instrument_id, request):
        portfolio = (
            await self.session.execute(
                select(PaperPortfolio).where(PaperPortfolio.id == portfolio_id).with_for_update()
            )
        ).scalar_one_or_none()
        if portfolio is None:
            raise LookupError("Portefeuille introuvable.")
        instrument = await self.session.get(MarketInstrument, instrument_id)
        if instrument is None:
            raise LookupError("Titre introuvable.")
        data = request.model_dump(mode="json")
        actions = (
            (
                await self.session.execute(
                    select(PortfolioAction).where(
                        PortfolioAction.portfolio_id == portfolio_id,
                        PortfolioAction.instrument_id == instrument_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for action in actions:
            if action.kind == request.kind and action.effective_date == request.effective_date:
                if action.data["request"] != data:
                    raise ValueError(
                        "Opération déjà enregistrée avec d’autres données ; aucun écrasement."
                    )
                return {"id": action.id, "inserted": False, **action.data}
        trades = (
            (
                await self.session.execute(
                    select(PaperTrade).where(
                        PaperTrade.portfolio_id == portfolio_id,
                        PaperTrade.instrument_id == instrument_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        held = entitled_quantity(trades, actions, request.effective_date)
        if request.kind == "dividend" and any(
            a.kind == "split" and a.effective_date == request.effective_date for a in actions
        ):
            raise ValueError("Split et détachement le même jour : convention par titre ambiguë.")
        evidence = {
            "request": data,
            "symbol": instrument.symbol,
            "exchange": instrument.exchange,
            "quantity_entitled": held,
            "cash_delta": "0.00",
            "conversion": None,
        }
        if request.kind == "dividend":
            if request.currency != instrument.currency:
                raise ValueError(
                    "Le dividende doit être exprimé dans la devise principale du titre."
                )
            # A net amount is already per share in major currency, never quote subunits.
            rate = None
            if instrument.currency != "USD":
                rate = (
                    await self.session.execute(
                        select(FxRate)
                        .where(
                            FxRate.currency == instrument.currency,
                            FxRate.rate_date <= request.payment_date,
                        )
                        .order_by(FxRate.rate_date.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if (
                    rate is None
                    or (request.payment_date - rate.rate_date).days
                    > get_settings().market_max_fx_age_days
                ):
                    raise ValueError("Taux daté manquant ou trop ancien à la date du paiement.")
            cash = money(
                Decimal(held)
                * request.net_amount_per_security
                * (rate.usd_per_unit if rate else Decimal(1))
            )
            evidence["cash_delta"] = str(cash)
            evidence["conversion"] = {
                "currency": instrument.currency,
                "usd_per_unit": str(rate.usd_per_unit) if rate else "1",
                "fx_date": rate.rate_date.isoformat() if rate else None,
                "fx_source_url": rate.source_url if rate else None,
                "fx_fetched_at": rate.fetched_at.isoformat() if rate else None,
                "fx_provider": rate.provider if rate else None,
                "fx_derivation": rate.derivation if rate else None,
            }
            if portfolio.cash + cash >= Decimal("1000000000000000000"):
                raise ValueError("Capital hors capacité.")
            portfolio.cash += cash
        else:
            # A late split would require re-executing trades and fees; refuse that rewrite.
            if any(
                t.executed_at.astimezone(UTC).date() >= request.effective_date for t in trades
            ) or any(a.effective_date >= request.effective_date for a in actions):
                raise ValueError(
                    "Split rétroactif incompatible avec des opérations déjà enregistrées."
                )
            position = (
                await self.session.execute(
                    select(PaperPosition).where(
                        PaperPosition.portfolio_id == portfolio_id,
                        PaperPosition.instrument_id == instrument_id,
                    )
                )
            ).scalar_one_or_none()
            if position is None or position.quantity != held or held <= 0:
                raise ValueError("Aucune position antérieure compatible avec ce split.")
            price = await MarketDataService(self.session).latest_price(instrument_id)
            if price is None or price.session_date < request.effective_date:
                raise ValueError("Une clôture brute postérieure ou égale au split est requise.")
            position.quantity = split_quantity(held, request.numerator, request.denominator)
            evidence["quantity_after"] = position.quantity
            # Total cost basis is unchanged; trade prices and their conversions stay immutable.
        action = PortfolioAction(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            kind=request.kind,
            effective_date=request.effective_date,
            observed_at=datetime.now(UTC),
            data=evidence,
        )
        self.session.add(action)
        await self.session.flush()
        await PortfolioHistoryService(self.session).capture(portfolio_id, commit=False)
        await self.session.commit()
        return {"id": action.id, "inserted": True, **evidence}
