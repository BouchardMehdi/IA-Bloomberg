from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes.events import get_event_service
from app.main import app
from app.schemas.event import EventCompanyRead, EventPage, EventRead


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
                    status="enriched",
                    extraction_method="deterministic",
                    extraction_version="deterministic-v1",
                    evidence_excerpt="Filed: 2026-09-30",
                    structured_data={
                        "form": "8-K",
                        "company_name": "Example Corporation",
                        "cik": "0001234567",
                    },
                    confidence_score=1.0,
                    country="US",
                    region="NORTH_AMERICA",
                    source_name="SEC EDGAR 8-K",
                    article_url="https://www.sec.gov/example",
                    companies=[
                        EventCompanyRead(
                            id=UUID("00000000-0000-0000-0000-000000000004"),
                            cik="0001234567",
                            name="Example Corporation",
                            role="subject",
                        )
                    ],
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
    assert payload["items"][0]["companies"][0]["cik"] == "0001234567"


def test_events_endpoint_validates_page_size() -> None:
    response = client.get("/api/v1/events?limit=101")
    assert response.status_code == 422
