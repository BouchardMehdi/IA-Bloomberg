from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.market import InstrumentCreate, PaperOrder, PortfolioCreate
from app.services.market_data import MarketDataService
from app.services.paper_portfolio import PaperPortfolioService

router = APIRouter()
Db = Annotated[AsyncSession, Depends(get_db_session)]


def market_response(data: dict, status_code: int = 200) -> JSONResponse:
    # Exact monetary decimals in the public contract, without binary float conversion.
    return JSONResponse(
        jsonable_encoder(data, custom_encoder={Decimal: str}), status_code=status_code
    )


@router.get("/instruments")
async def instruments(session: Db):
    return market_response(await MarketDataService(session).list_instruments())


@router.post("/instruments", status_code=201)
async def add_instrument(request: InstrumentCreate, session: Db):
    try:
        return market_response(await MarketDataService(session).add_instrument(request), 201)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/instruments/{instrument_id}/prices")
async def prices(
    instrument_id: UUID, session: Db, limit: Annotated[int, Query(ge=1, le=1000)] = 100
):
    result = await MarketDataService(session).history(instrument_id, limit)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.get("/portfolios")
async def portfolios(session: Db):
    return market_response(await PaperPortfolioService(session).list_portfolios())


@router.post("/portfolios", status_code=201)
async def create_portfolio(request: PortfolioCreate, session: Db):
    return market_response(await PaperPortfolioService(session).create(request), 201)


@router.get("/portfolios/{portfolio_id}")
async def portfolio_detail(portfolio_id: UUID, session: Db):
    result = await PaperPortfolioService(session).snapshot(portfolio_id)
    if result is None:
        raise HTTPException(404, "Portefeuille introuvable.")
    return market_response(result)


@router.post("/portfolios/{portfolio_id}/orders")
async def paper_order(portfolio_id: UUID, request: PaperOrder, session: Db):
    try:
        return market_response(await PaperPortfolioService(session).order(portfolio_id, request))
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None
