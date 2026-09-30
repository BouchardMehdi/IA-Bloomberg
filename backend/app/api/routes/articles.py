from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.article import ArticlePage
from app.services.articles import ArticleService

router = APIRouter()


def get_article_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ArticleService:
    return ArticleService(session)


@router.get("", response_model=ArticlePage)
async def list_articles(
    service: Annotated[ArticleService, Depends(get_article_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArticlePage:
    return await service.list_latest(limit=limit, offset=offset)
