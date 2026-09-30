from fastapi.testclient import TestClient

from app.main import app
from app.services.health import get_health_service


class ReadyHealthService:
    async def check_dependencies(self) -> dict[str, bool]:
        return {"postgres": True, "redis": True}


class DegradedHealthService:
    async def check_dependencies(self) -> dict[str, bool]:
        return {"postgres": True, "redis": False}


client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_when_dependencies_are_available() -> None:
    app.dependency_overrides[get_health_service] = ReadyHealthService
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"postgres": True, "redis": True},
    }


def test_readiness_when_a_dependency_is_unavailable() -> None:
    app.dependency_overrides[get_health_service] = DegradedHealthService
    try:
        response = client.get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
