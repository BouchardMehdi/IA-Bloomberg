import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.ai_worker import router as worker_router
from app.core.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API de veille économique et financière structurée.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")
app.include_router(worker_router, prefix="/api/v1/ai-worker", tags=["local AI worker"])


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
