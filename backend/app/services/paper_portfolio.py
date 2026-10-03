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
from app.schemas.market import PaperOrder, PortfolioCreate
from app.services.market_data import MarketDataService


class PaperPortfolioService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.market = MarketDataService(session)

    async def create(self, request: PortfolioCreate) -> dict:
        portfolio = PaperPortfolio(**request.model_dump(), cash=request.initial_capital)
        self.session.add(portfolio)
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
            )
        ).all()
        holdings = []
        total = portfolio.cash
        all_priced = True
        for position, instrument in positions:
            price = await self.market.latest_price(instrument.id)
            value = money(price.close * position.quantity) if price else None
            all_priced &= price is not None
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
                    "quote_date": price.session_date if price else None,
                    "source_url": price.source_url if price else None,
                    "stale": price is None
                    or (datetime.now(UTC).date() - price.session_date).days
                    > get_settings().market_max_price_age_days,
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
                select(PaperTrade, MarketInstrument.symbol)
                .join(
                    MarketInstrument,
                    MarketInstrument.id == PaperTrade.instrument_id,
                )
                .where(PaperTrade.portfolio_id == portfolio_id)
                .order_by(PaperTrade.executed_at.desc())
                .limit(50)
            )
        ).all()
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
            "total_value": total if all_priced else None,
            "total_pnl": total - portfolio.initial_capital if all_priced else None,
            "return_pct": money((total / portfolio.initial_capital - 1) * 100)
            if all_priced
            else None,
            "realized_pnl": realized,
            "valuation_stale": any(h["stale"] for h in holdings),
            "positions": holdings,
            "trades": [self.trade_read(t, symbol) for t, symbol in trades],
        }

    @staticmethod
    def trade_read(trade, symbol) -> dict:
        return {
            "id": trade.id,
            "client_order_id": trade.client_order_id,
            "instrument_id": trade.instrument_id,
            "symbol": symbol,
            "side": trade.side,
            "quantity": trade.quantity,
            "price": trade.price,
            "fee": trade.fee,
            "realized_pnl": trade.realized_pnl,
            "quote_date": trade.quote_date,
            "quote_source_url": trade.quote_source_url,
            "executed_at": trade.executed_at,
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
            return self.trade_read(existing, instrument.symbol)
        instrument = await self.session.get(MarketInstrument, request.instrument_id)
        if instrument is None:
            raise LookupError("Titre introuvable.")
        if request.side == "buy":
            universe = await self.session.get(EntityRegistry, "wls_universe")
            if eligibility(instrument, universe)["status"] != "verified":
                raise ValueError("Achat refusé : action non vérifiée dans l'export officiel WLS.")
        today = datetime.now(UTC).date()
        if (portfolio.starts_on and today < portfolio.starts_on) or (
            portfolio.ends_on and today > portfolio.ends_on
        ):
            raise ValueError("La simulation est en dehors des dates du challenge configurées.")
        if portfolio.allowed_symbols and instrument.symbol not in portfolio.allowed_symbols:
            raise ValueError("Titre non autorisé dans ce portefeuille.")
        if instrument.currency != portfolio.currency:
            raise ValueError("La devise du titre ne correspond pas au portefeuille.")
        quote = await self.market.latest_price(instrument.id)
        if (
            quote is None
            or not 0
            <= (today - quote.session_date).days
            <= get_settings().market_max_price_age_days
        ):
            raise ValueError(
                "Cours absent ou trop ancien : synchroniser les cours avant de simuler."
            )
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
            price=quote.close,
            fee_bps=portfolio.fee_bps,
        )
        if request.side == "buy":
            snapshot = await self.snapshot(portfolio_id)
            if snapshot["total_value"] is None or snapshot["valuation_stale"]:
                raise ValueError(
                    "Actualiser les autres positions avant de contrôler la concentration."
                )
            nav_after = snapshot["total_value"] - fill.fee
            check_concentration(fill.quantity * quote.close, nav_after, portfolio.max_position_pct)
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
            price=quote.close,
            fee=fill.fee,
            realized_pnl=fill.realized_pnl,
            quote_date=quote.session_date,
            quote_source_url=quote.source_url,
            executed_at=datetime.now(UTC),
        )
        self.session.add(trade)
        await self.session.commit()
        return self.trade_read(trade, instrument.symbol)
