from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes.articles import get_article_service
from app.main import app
from app.schemas.article import ArticlePage, ArticleRead


class StubArticleService:
    async def list_latest(self, limit: int, offset: int) -> ArticlePage:
        return ArticlePage(
            items=[
                ArticleRead(
                    id=UUID("00000000-0000-0000-0000-000000000001"),
                    source_name="European Central Bank",
                    url="https://www.ecb.europa.eu/example",
                    title="Monetary policy decisions",
                    content="Rates remain unchanged.",
                    language="en",
                    published_at=datetime(2026, 9, 24, 12, 15, tzinfo=UTC),
                    fetched_at=datetime(2026, 9, 24, 12, 16, tzinfo=UTC),
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
        )


client = TestClient(app)


def test_articles_endpoint_returns_paginated_articles() -> None:
    app.dependency_overrides[get_article_service] = StubArticleService
    try:
        response = client.get("/api/v1/articles?limit=10&offset=0")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["source_name"] == "European Central Bank"


def test_articles_endpoint_validates_page_size() -> None:
    response = client.get("/api/v1/articles?limit=101")
    assert response.status_code == 422
