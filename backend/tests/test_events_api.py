from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes.events import get_event_service
from app.main import app
from app.schemas.event import EventCompanyRead, EventPage, EventRead


class StubEventService:
    async def analysis_detail(self, event_id: UUID) -> dict | None:
        if str(event_id) != "00000000-0000-0000-0000-000000000003":
            return None
        return {
            "id": UUID("00000000-0000-0000-0000-000000000009"),
            "status": "partial",
            "source_url": "https://www.sec.gov/example",
            "model_name": "fixture-model",
            "prompt_version": "semantic-v5-passages",
            "coverage": {"analyzed_count": 1},
            "passages": [
                {
                    "index": 2,
                    "start": 9000,
                    "end": 9044,
                    "text": "The company approved a material acquisition.",
                    "status": "success",
                    "result": {"events": []},
                    "error_message": None,
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                }
            ],
        }

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
                    entity_resolution={
                        "version": "entities-v1",
                        "resolved_at": datetime(2026, 10, 3, tzinfo=UTC),
                        "registry": {
                            "url": "https://www.sec.gov/files/company_tickers_exchange.json",
                            "observed_at": "2026-10-03T00:00:00Z",
                            "published_at": None,
                        },
                        "entities": [
                            {
                                "name": "Example Corporation",
                                "kind": "company",
                                "role": "source_subject",
                                "quote": None,
                                "status": "resolved",
                                "method": "filing_cik",
                                "candidates": [
                                    {
                                        "cik": "0001234567",
                                        "name": "Example Corporation",
                                        "listings": [{"ticker": "EX", "exchange": "NYSE"}],
                                    }
                                ],
                            }
                        ],
                    },
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
    resolution = payload["items"][0]["entity_resolution"]
    assert resolution["registry"]["published_at"] is None
    assert resolution["entities"][0]["candidates"][0]["listings"][0]["ticker"] == "EX"


def test_events_endpoint_validates_page_size() -> None:
    response = client.get("/api/v1/events?limit=101")
    assert response.status_code == 422


def test_analysis_detail_exposes_passage_text_offsets_and_unknown_event_returns_404() -> None:
    app.dependency_overrides[get_event_service] = StubEventService
    try:
        response = client.get("/api/v1/events/00000000-0000-0000-0000-000000000003/analysis")
        missing = client.get("/api/v1/events/00000000-0000-0000-0000-000000000099/analysis")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["coverage"]["analyzed_count"] == 1
    assert response.json()["passages"][0]["start"] == 9000
    assert "acquisition" in response.json()["passages"][0]["text"]
    assert missing.status_code == 404
