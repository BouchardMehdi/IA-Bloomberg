from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.routes.market import market_response
from app.api.routes.workspace import perform
from app.db.session import get_db_session
from app.schemas.journal import DecisionCreate, DecisionUpdate
from app.services.briefing import BriefingService
from app.services.collection_health import CollectionHealthService
from app.services.journal import JournalService

router = APIRouter()
Db = Annotated[object, Depends(get_db_session)]


@router.get("/collection-health")
async def collection_health(session: Db, family: Literal["sources", "market", "fx"] = "sources",
    limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000)):
    return market_response(await CollectionHealthService(session).detail(limit, offset, family))


@router.get("/briefing")
async def briefing(session: Db, day: date | None = None, portfolio_id: UUID | None = None,
    held_only: bool = False, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=1000)):
    return await perform(session, BriefingService(session).detail(day or datetime.now(UTC).date(), portfolio_id, limit, offset, held_only))


@router.get("/journal")
async def journal(session: Db, status: Literal["watching", "considering", "held", "closed", "invalidated"] | None = None,
    instrument_id: UUID | None = None, portfolio_id: UUID | None = None,
    limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000)):
    return market_response(await JournalService(session).listing(status, instrument_id, portfolio_id, limit, offset))


@router.post("/journal")
async def create_decision(data: DecisionCreate, request: Request, session: Db):
    return await perform(session, JournalService(session).save(data, request.state.actor))


@router.get("/journal/{identifier}")
async def decision(identifier: UUID, session: Db, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000)):
    return await perform(session, JournalService(session).detail(identifier, limit, offset))


@router.post("/journal/{identifier}/revisions")
async def revise_decision(identifier: UUID, data: DecisionUpdate, request: Request, session: Db):
    return await perform(session, JournalService(session).save(data, request.state.actor, identifier))
