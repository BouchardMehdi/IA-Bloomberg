from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.collection_run import CollectionRunPage
from app.services.collection_runs import CollectionRunService

router = APIRouter()


def get_collection_run_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CollectionRunService:
    return CollectionRunService(session)


@router.get("", response_model=CollectionRunPage)
async def list_collection_runs(
    service: Annotated[CollectionRunService, Depends(get_collection_run_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CollectionRunPage:
    return await service.list_latest(limit=limit, offset=offset)
