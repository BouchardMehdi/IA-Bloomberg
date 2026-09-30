from fastapi import APIRouter

from app.api.routes import articles, collection_runs, health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(articles.router, prefix="/articles", tags=["articles"])
api_router.include_router(
    collection_runs.router,
    prefix="/collection-runs",
    tags=["collection-runs"],
)
