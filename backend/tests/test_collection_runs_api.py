from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes.collection_runs import get_collection_run_service
from app.main import app
from app.schemas.collection_run import CollectionRunPage, CollectionRunRead


class StubCollectionRunService:
    async def list_latest(self, limit: int, offset: int) -> CollectionRunPage:
        return CollectionRunPage(
            items=[
                CollectionRunRead(
                    id=UUID("00000000-0000-0000-0000-000000000002"),
                    source_name="European Central Bank",
                    trigger="scheduled",
                    status="success",
                    started_at=datetime(2026, 9, 30, 8, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 9, 30, 8, 0, 2, tzinfo=UTC),
                    duration_ms=2000,
                    fetched_count=15,
                    inserted_count=0,
                    duplicate_count=15,
                    error_message=None,
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
        )


client = TestClient(app)


def test_collection_runs_endpoint_returns_history() -> None:
    app.dependency_overrides[get_collection_run_service] = StubCollectionRunService
    try:
        response = client.get("/api/v1/collection-runs?limit=5")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["status"] == "success"
    assert payload["items"][0]["duplicate_count"] == 15
