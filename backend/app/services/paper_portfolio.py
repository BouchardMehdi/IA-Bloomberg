from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.market.paper import calculate_fill, check_concentration, money
from app.market.wls import eligibility
from app.models.entity_registry import EntityRegistry
from app.models.market import MarketInstrument
from app.models.portfolio import PaperPortfolio, PaperPosition, PaperTrade
from app.models.portfolio_tracking import PortfolioAction
from app.schemas.market import PaperOrder, PortfolioCreate
from app.services.market_data import MarketDataService
from app.services.usd_valuation import UsdValuationService
from app.services.wls_automation import WlsAutomationService


class PaperPortfolioService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.market = MarketDataService(session)
        self.valuation = UsdValuationService(session)

    async def create(self, request: PortfolioCreate) -> dict:
        portfolio = PaperPortfolio(**request.model_dump(), cash=request.initial_capital)
        self.session.add(portfolio)
        await self.session.flush()
        from app.services.portfolio_history import PortfolioHistoryService

        await PortfolioHistoryService(self.session).capture(portfolio.id, commit=False)
        await self.session.commit()
        return {"id": portfolio.id, "name": portfolio.name}

    async def list_portfolios(self) -> dict:
        rows = (
            (await self.session.execute(select(PaperPortfolio).order_by(PaperPortfolio.created_at)))
            .scalars()
            .all()
        )
        return {
            "items": [
                {
                    "id": p.id,
                    "name": p.name,
                    "currency": p.currency,
                    "initial_capital": p.initial_capital,
                }
                for p in rows
            ]
        }

    async def snapshot(self, portfolio_id: UUID) -> dict | None:
        portfolio = await self.session.get(PaperPortfolio, portfolio_id)
        if portfolio is None:
            return None
        positions = (
            await self.session.execute(
                select(PaperPosition, MarketInstrument)
                .join(
                    MarketInstrument,
                    MarketInstrument.id == PaperPosition.instrument_id,
                )
                .where(PaperPosition.portfolio_id == portfolio_id, PaperPosition.quantity > 0)
                .order_by(PaperPosition.instrument_id)
            )
        ).all()
        holdings = []
        total = portfolio.cash
        all_priced = True
        for position, instrument in positions:
            price = await self.market.latest_price(instrument.id)
            valuation = await self.valuation.quote(instrument, price)
            value = (
                money(valuation["price_usd"] * position.quantity)
                if valuation["price_usd"] is not None
                else None
            )
            all_priced &= value is not None
            if value is not None:
                total += value
            holdings.append(
                {
                    "instrument_id": instrument.id,
                    "symbol": instrument.symbol,
                    "exchange": instrument.exchange,
                    "name": instrument.name,
                    "quantity": position.quantity,
                    "cost_basis": position.cost_basis,
                    "value": value,
                    "unrealized_pnl": value - position.cost_basis if value is not None else None,
                    "price": price.close if price else None,
                    "currency": instrument.currency,
                    "usd_valuation": valuation,
                    "quote_date": price.session_date if price else None,
                    "source_url": price.source_url if price else None,
                    "stale": valuation["stale"],
                }
            )
        realized = (
            await self.session.execute(
                select(func.coalesce(func.sum(PaperTrade.realized_pnl), 0)).where(
                    PaperTrade.portfolio_id == portfolio_id,
                )
            )
        ).scalar_one()
        trades = (
            await self.session.execute(
                select(PaperTrade, MarketInstrument.symbol, MarketInstrument.exchange)
                .join(
                    MarketInstrument,
                    MarketInstrument.id == PaperTrade.instrument_id,
                )
                .where(PaperTrade.portfolio_id == portfolio_id)
                .order_by(PaperTrade.executed_at.desc())
                .limit(50)
            )
        ).all()
        actions = (
            (
                await self.session.execute(
                    select(PortfolioAction)
                    .where(PortfolioAction.portfolio_id == portfolio_id)
                    .order_by(PortfolioAction.id)
                )
            )
            .scalars()
            .all()
        )
        dividend_income = sum(
            (Decimal(a.data["cash_delta"]) for a in actions if a.kind == "dividend"), Decimal("0")
        )
        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "currency": portfolio.currency,
            "initial_capital": portfolio.initial_capital,
            "cash": portfolio.cash,
            "fee_bps": portfolio.fee_bps,
            "max_position_pct": portfolio.max_position_pct,
            "allowed_symbols": portfolio.allowed_symbols,
            "starts_on": portfolio.starts_on,
            "ends_on": portfolio.ends_on,
            "wls_policy": portfolio.wls_policy,
            "total_value": total if all_priced else None,
            "total_pnl": total - portfolio.initial_capital if all_priced else None,
            "return_pct": money((total / portfolio.initial_capital - 1) * 100)
            if all_priced
            else None,
            "realized_pnl": realized,
            "dividend_income": dividend_income,
            "action_ids": [a.id for a in actions],
            "valuation_stale": any(h["stale"] for h in holdings),
            "positions": holdings,
            "trades": [self.trade_read(t, symbol, exchange) for t, symbol, exchange in trades],
        }

    @staticmethod
    def trade_read(trade, symbol, exchange) -> dict:
        return {
            "id": trade.id,
            "client_order_id": trade.client_order_id,
            "instrument_id": trade.instrument_id,
            "symbol": symbol,
            "exchange": exchange,
            "price_currency": "USD",
            "side": trade.side,
            "quantity": trade.quantity,
            "price": trade.price,
            "fee": trade.fee,
            "realized_pnl": trade.realized_pnl,
            "quote_date": trade.quote_date,
            "quote_source_url": trade.quote_source_url,
            "executed_at": trade.executed_at,
            "conversion": trade.conversion,
            "universe_evidence": trade.universe_evidence,
        }

    async def order(self, portfolio_id: UUID, request: PaperOrder) -> dict:
        # One ledger writer at a time. Cash, position and immutable trade commit together.
        portfolio = (
            await self.session.execute(
                select(PaperPortfolio)
                .where(
                    PaperPortfolio.id == portfolio_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if portfolio is None:
            raise LookupError("Portefeuille introuvable.")
        existing = (
            await self.session.execute(
                select(PaperTrade).where(
                    PaperTrade.portfolio_id == portfolio_id,
                    PaperTrade.client_order_id == request.client_order_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if (
                existing.instrument_id != request.instrument_id
                or existing.side != request.side
                or existing.quantity != request.quantity
            ):
                raise ValueError(
                    "Cet identifiant de simulation est déjà utilisé pour un autre ordre."
                )
            instrument = await self.session.get(MarketInstrument, existing.instrument_id)
            return self.trade_read(existing, instrument.symbol, instrument.exchange)
        instrument = await self.session.get(MarketInstrument, request.instrument_id)
        if instrument is None:
            raise LookupError("Titre introuvable.")
        universe_evidence = None
        if request.side == "buy":
            universe = await self.session.get(EntityRegistry, "wls_universe")
            membership = eligibility(instrument, universe)
            if membership["status"] == "verified":
                universe_evidence = membership | {
                    "policy": "verified",
                    "source_hash": universe.content_hash,
                }
            elif portfolio.wls_policy == "declared_partial":
                preparation = (await WlsAutomationService(self.session).assessments([instrument]))[
                    str(instrument.id)
                ]
                if preparation["status"] != "matched":
                    raise ValueError(
                        "Achat provisoire refusé : correspondance de cotation "
                        "ou classification d'action ordinaire non résolue."
                    )
                universe_evidence = preparation["evidence"] | {"policy": "declared_partial"}
            else:
                raise ValueError("Achat refusé : action non vérifiée dans l'export officiel WLS.")
        today = datetime.now(UTC).date()
        if (portfolio.starts_on and today < portfolio.starts_on) or (
            portfolio.ends_on and today > portfolio.ends_on
        ):
            raise ValueError("La simulation est en dehors des dates du challenge configurées.")
        if portfolio.allowed_symbols and instrument.symbol not in portfolio.allowed_symbols:
            raise ValueError("Titre non autorisé dans ce portefeuille.")
        quote = await self.market.latest_price(instrument.id)
        last_split = (
            await self.session.execute(
                select(func.max(PortfolioAction.effective_date)).where(
                    PortfolioAction.portfolio_id == portfolio_id,
                    PortfolioAction.instrument_id == instrument.id,
                    PortfolioAction.kind == "split",
                )
            )
        ).scalar_one()
        if last_split and (quote is None or quote.session_date < last_split):
            raise ValueError("Cours antérieur au split enregistré : actualiser la clôture brute.")
        if (
            quote is None
            or not 0
            <= (today - quote.session_date).days
            <= get_settings().market_max_price_age_days
        ):
            raise ValueError(
                "Cours absent ou trop ancien : synchroniser les cours avant de simuler."
            )
        valuation = await self.valuation.quote(instrument, quote, today)
        if valuation["price_usd"] is None or valuation["stale"]:
            raise ValueError(
                "Conversion USD absente, invalide ou trop ancienne : actualiser les données."
            )
        usd_price = valuation["price_usd"]
        position = (
            await self.session.execute(
                select(PaperPosition).where(
                    PaperPosition.portfolio_id == portfolio_id,
                    PaperPosition.instrument_id == instrument.id,
                )
            )
        ).scalar_one_or_none()
        fill = calculate_fill(
            cash=portfolio.cash,
            held=position.quantity if position else 0,
            cost_basis=position.cost_basis if position else Decimal("0"),
            side=request.side,
            quantity=request.quantity,
            price=usd_price,
            fee_bps=portfolio.fee_bps,
        )
        if request.side == "buy":
            snapshot = await self.snapshot(portfolio_id)
            if snapshot["total_value"] is None or snapshot["valuation_stale"]:
                raise ValueError(
                    "Actualiser les autres positions avant de contrôler la concentration."
                )
            nav_after = snapshot["total_value"] - fill.fee
            check_concentration(fill.quantity * usd_price, nav_after, portfolio.max_position_pct)
        portfolio.cash = fill.cash
        if position is None:
            position = PaperPosition(portfolio_id=portfolio_id, instrument_id=instrument.id)
            self.session.add(position)
        position.quantity = fill.quantity
        position.cost_basis = fill.cost_basis
        trade = PaperTrade(
            portfolio_id=portfolio_id,
            instrument_id=instrument.id,
            client_order_id=request.client_order_id,
            side=request.side,
            quantity=request.quantity,
            price=usd_price,
            fee=fill.fee,
            realized_pnl=fill.realized_pnl,
            quote_date=quote.session_date,
            quote_source_url=quote.source_url,
            executed_at=datetime.now(UTC),
            universe_evidence=universe_evidence,
            conversion=valuation["conversion"]
            if instrument.currency != "USD" or instrument.quote_multiplier != 1
            else None,
        )
        self.session.add(trade)
        await self.session.flush()
        from app.services.portfolio_history import PortfolioHistoryService

        await PortfolioHistoryService(self.session).capture(portfolio_id, commit=False)
        await self.session.commit()
        return self.trade_read(trade, instrument.symbol, instrument.exchange)
