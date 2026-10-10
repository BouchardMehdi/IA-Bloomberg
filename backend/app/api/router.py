from fastapi import APIRouter, Depends

from app.api.routes import access, articles, collection_runs, events, health, market, workspace
from app.services.access import access_guard

api_router = APIRouter(dependencies=[Depends(access_guard)])
api_router.include_router(access.router, prefix="/auth", tags=["workspace access"])
api_router.include_router(workspace.router, prefix="/workspace", tags=["workspace"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(market.router, prefix="/market", tags=["market simulation"])
api_router.include_router(
    collection_runs.router,
    prefix="/collection-runs",
    tags=["collection-runs"],
)
