from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.market.earnings_calendar import EarningsCalendarClient
from app.schemas.earnings import EarningsInput
from app.schemas.international import FxRateCreate, InternationalInstrumentCreate, LocalPriceCreate
from app.schemas.market import InstrumentCreate, PaperOrder, PortfolioCreate
from app.schemas.valuation import ValuationInput
from app.schemas.wls_candidates import CandidateMapping
from app.services.company_publications import CompanyPublicationService
from app.services.earnings import EarningsService
from app.services.financial_results import FinancialResultsService
from app.services.financial_trends import FinancialTrendsService
from app.services.fx_collection import FxCollectionService
from app.services.instrument_research import InstrumentResearchService
from app.services.international_market import InternationalMarketService
from app.services.market_data import MarketDataService
from app.services.opportunity import OpportunityService
from app.services.paper_portfolio import PaperPortfolioService
from app.services.research_ranking import ResearchRankingService
from app.services.valuation import ValuationService
from app.services.wls_candidates import WlsCandidateService

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


@router.get("/wls-candidates")
async def wls_candidates(
    session: Db,
    search: Annotated[str, Query(max_length=100)] = "",
    offset: Annotated[int, Query(ge=0, le=20000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return market_response(await WlsCandidateService(session).detail(search, offset, limit))


@router.post("/wls-candidates/mappings")
async def map_wls_candidate(request: CandidateMapping, session: Db):
    try:
        return market_response(await WlsCandidateService(session).map_listing(request))
    except LookupError as exc:
        await session.rollback()
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.get("/instruments/{instrument_id}/publications/collection")
async def company_publication_status(instrument_id: UUID, session: Db):
    result = await CompanyPublicationService(session).status(instrument_id)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.get("/instruments/{instrument_id}/financials")
async def financial_results(
    instrument_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=20000)] = 0,
):
    result = await FinancialResultsService(session).detail(instrument_id, limit, offset)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.post("/instruments/{instrument_id}/financials/collect")
async def collect_financial_results(instrument_id: UUID, session: Db):
    try:
        return market_response(await FinancialResultsService(session).collect(instrument_id))
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.get("/instruments/{instrument_id}/financial-trends")
async def financial_trends(instrument_id: UUID, session: Db):
    result = await FinancialTrendsService(session).detail(instrument_id)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.get("/instruments/{instrument_id}/valuation")
async def valuation(instrument_id: UUID, session: Db):
    result = await ValuationService(session).detail(instrument_id)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.post("/instruments/{instrument_id}/valuation", status_code=201)
async def add_valuation(instrument_id: UUID, request: ValuationInput, session: Db):
    try:
        return market_response(await ValuationService(session).add(instrument_id, request), 201)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.post("/instruments/{instrument_id}/publications/collect")
async def collect_company_publications(instrument_id: UUID, session: Db):
    try:
        return market_response(await CompanyPublicationService(session).collect(instrument_id))
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.get("/instruments/{instrument_id}/earnings")
async def earnings(
    instrument_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=20000)] = 0,
):
    result = await EarningsService(session).detail(instrument_id, limit, offset)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.post("/instruments/{instrument_id}/earnings", status_code=201)
async def add_earnings(instrument_id: UUID, request: EarningsInput, session: Db):
    try:
        return market_response(await EarningsService(session).add(instrument_id, request), 201)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.post("/instruments/{instrument_id}/earnings/collect")
async def collect_earnings(instrument_id: UUID, session: Db):
    settings = get_settings()
    key = settings.alpha_vantage_api_key.get_secret_value()
    if not key:
        raise HTTPException(503, "Clé Alpha Vantage non configurée côté serveur.")
    try:
        return market_response(
            await EarningsService(session).collect(
                instrument_id,
                EarningsCalendarClient(
                    key, daily_request_budget=settings.market_daily_request_budget
                ),
            )
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.get("/price-collection")
async def price_collection_status(session: Db):
    return market_response(await MarketDataService(session).collection_status())


@router.get("/research-ranking")
async def research_ranking(
    session: Db,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=20000)] = 0,
):
    return market_response(await ResearchRankingService(session).ranking(limit, offset))


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


@router.post("/international-instruments", status_code=201)
async def add_international_instrument(request: InternationalInstrumentCreate, session: Db):
    try:
        return market_response(
            await InternationalMarketService(session).add_instrument(request), 201
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            409, "Identité de titre déjà enregistrée : vérifier les identifiants."
        ) from None


@router.post("/instruments/{instrument_id}/prices")
async def supply_local_price(instrument_id: UUID, request: LocalPriceCreate, session: Db):
    try:
        return market_response(
            await InternationalMarketService(session).save_price(instrument_id, request)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(400, str(exc)) from None


@router.get("/fx-rates")
async def fx_rates(session: Db):
    return market_response(await InternationalMarketService(session).rates())


@router.get("/fx-collection")
async def fx_collection_status(session: Db):
    return market_response(await FxCollectionService(session).status())


@router.post("/fx-rates")
async def supply_fx(request: FxRateCreate, session: Db):
    return market_response(await InternationalMarketService(session).save_fx(request))


@router.get("/portfolios")
async def portfolios(session: Db):
    return market_response(await PaperPortfolioService(session).list_portfolios())


@router.get("/instruments/{instrument_id}/research")
async def instrument_research(
    instrument_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    result = await InstrumentResearchService(session).detail(instrument_id, limit, offset)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


@router.get("/instruments/{instrument_id}/opportunity")
async def opportunity(instrument_id: UUID, session: Db):
    result = await OpportunityService(session).detail(instrument_id)
    if result is None:
        raise HTTPException(404, "Titre introuvable.")
    return market_response(result)


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
