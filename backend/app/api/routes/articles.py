from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.article import ArticleDetail, ArticlePage
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


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: UUID,
    service: Annotated[ArticleService, Depends(get_article_service)],
) -> ArticleDetail:
    article = await service.get(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
