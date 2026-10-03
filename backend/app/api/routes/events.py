from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.event import AnalysisDetail, EventPage
from app.services.events import EventService

router = APIRouter()


def get_event_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EventService:
    return EventService(session)


@router.get("", response_model=EventPage)
async def list_events(
    service: Annotated[EventService, Depends(get_event_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventPage:
    return await service.list_latest(limit=limit, offset=offset)


@router.get("/{event_id}/analysis", response_model=AnalysisDetail)
async def analysis_detail(
    event_id: UUID, service: Annotated[EventService, Depends(get_event_service)]
) -> dict:
    detail = await service.analysis_detail(event_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="No analysis for this event")
    return detail
