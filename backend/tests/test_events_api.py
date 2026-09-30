from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes.events import get_event_service
from app.main import app
from app.schemas.event import EventPage, EventRead


class StubEventService:
    async def list_latest(self, limit: int, offset: int) -> EventPage:
        return EventPage(
            items=[
                EventRead(
                    id=UUID("00000000-0000-0000-0000-000000000003"),
                    event_type="regulatory_filing",
                    title="8-K - Example Corporation",
                    description="Filed: 2026-09-30",
                    event_datetime=datetime(2026, 9, 30, 20, 0, tzinfo=UTC),
                    status="detected",
                    confidence_score=1.0,
                    country="US",
                    region="NORTH_AMERICA",
                    source_name="SEC EDGAR 8-K",
                    article_url="https://www.sec.gov/example",
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
        )


client = TestClient(app)


def test_events_endpoint_returns_traceable_events() -> None:
    app.dependency_overrides[get_event_service] = StubEventService
    try:
        response = client.get("/api/v1/events?limit=10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_type"] == "regulatory_filing"
    assert payload["items"][0]["article_url"] == "https://www.sec.gov/example"


def test_events_endpoint_validates_page_size() -> None:
    response = client.get("/api/v1/events?limit=101")
    assert response.status_code == 422
