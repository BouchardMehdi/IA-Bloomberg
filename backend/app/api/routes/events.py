from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.event import EventPage
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
