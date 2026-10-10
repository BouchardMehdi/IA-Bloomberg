import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.api.routes import ai_worker
from app.core.config import Settings
from app.db.session import get_db_session
from app.semantic.client import configured_semantic_client
from app.semantic.prompt import PROMPT_VERSION
from app.services.remote_ai import task_fingerprint
from app.worker.main import api_url, deliver, execute_task


def test_production_preflight_rejects_placeholder_contacts_weak_password_and_missing_backup(monkeypatch):
    from app.cli import check_production
    settings = SimpleNamespace(environment="production", ai_execution_mode="remote",
        database_url="postgresql+asyncpg://market_ai:" + "a" * 64 + "@postgres/market_ai",
        cors_origins=["https://market.company.test"], sec_user_agent="MarketAI/0.1 team@company.test")
    monkeypatch.setattr(check_production, "get_settings", lambda:settings)
    monkeypatch.setenv("ACME_EMAIL", "team@company.test")
    monkeypatch.setenv("SEC_USER_AGENT", settings.sec_user_agent)
    monkeypatch.setenv("BACKUP_RECIPIENT", "")
    check_production.check()
    with pytest.raises(ValueError, match="BACKUP_RECIPIENT"):
        check_production.check(require_backup=True)
    monkeypatch.setenv("ACME_EMAIL", "you@example.com")
    with pytest.raises(ValueError, match="ACME_EMAIL"):
        check_production.check()
    monkeypatch.setenv("ACME_EMAIL", "team@company.test")
    settings.database_url = "postgresql+asyncpg://market_ai:change-me@postgres/market_ai"
    with pytest.raises(ValueError, match="password"):
        check_production.check()


@pytest.mark.parametrize("url", ["http://example.org", "https://user:secret@example.org", "https://example.org/api", "https://example.org/?token=secret", "https://example.org/#x", ""])
def test_worker_requires_clean_https_origin(url):
    with pytest.raises(ValueError):
        api_url(url)


def test_worker_origin_and_task_identity():
    assert api_url("https://example.org/") == "https://example.org/api/v1/ai-worker"
    key = task_fingerprint("model", "SEC", "Title", "Text")
    assert key == task_fingerprint("model", "SEC", "Title", "Text")
    assert key != task_fingerprint("model2", "SEC", "Title", "Text")
    assert key != task_fingerprint("model", "SEC", "Title", "Other")


def test_remote_config_requires_hash_and_client_never_calls_ollama():
    with pytest.raises(ValidationError, match="AI_WORKER_TOKEN_SHA256"):
        Settings(_env_file=None, ai_execution_mode="remote", ai_worker_token_sha256="")
    settings = Settings(_env_file=None, ai_execution_mode="remote", ai_worker_token_sha256="a" * 64)
    assert type(configured_semantic_client(settings)).__name__ == "RemoteSemanticClient"


@pytest.mark.asyncio
async def test_scoped_worker_credentials_do_not_accept_cookie_or_bad_schema(monkeypatch):
    token = "fixture-only-credential-" + "x" * 32
    settings = SimpleNamespace(ai_worker_token_sha256=SimpleNamespace(get_secret_value=lambda:hashlib.sha256(token.encode()).hexdigest()),
        ai_execution_mode="remote", ai_analysis_enabled=True, ollama_model="fixture", ollama_timeout_seconds=30)
    monkeypatch.setattr(ai_worker, "get_settings", lambda: settings)
    session = SimpleNamespace(commit=AsyncMock())
    async def db():
        yield session
    app = FastAPI()
    app.include_router(ai_worker.router, prefix="/worker")
    app.dependency_overrides[get_db_session] = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as api:
        for headers in ({}, {"Cookie":"market_ai_session=browser"}, {"Authorization":"Bearer invalid"}):
            response = await api.post("/worker/claim", headers=headers, json={})
            assert response.status_code == 401
        api.headers["Authorization"] = f"Bearer {token}"
        assert (await api.post("/worker/claim", json={})).status_code == 422
        assert (await api.post("/worker/claim", content="x" * 2049)).status_code == 413
        assert (await api.post("/worker/claim", json={"model":"wrong", "prompt_version":PROMPT_VERSION})).status_code == 409
        assert (await api.post(f"/worker/{uuid4()}/complete", json={"lease_id":str(uuid4())})).status_code == 422
        settings.ai_analysis_enabled = False
        assert (await api.post("/worker/claim", json={})).status_code == 503


@pytest.mark.asyncio
async def test_delivery_replays_result_without_repeating_inference(monkeypatch):
    monkeypatch.setattr("app.worker.main.asyncio.sleep", AsyncMock())
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(502 if len(calls) == 1 else 200, json={"accepted":True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://test") as api:
        await deliver(api, {"id":str(uuid4())}, {"lease_id":str(uuid4()), "extraction":{"events":[]}})
    assert len(calls) == 2 and calls[0] == calls[1]


@pytest.mark.asyncio
async def test_worker_failure_sends_only_a_fixed_error_code(monkeypatch):
    monkeypatch.setattr("app.worker.main.OllamaSemanticClient", lambda *a, **k:SimpleNamespace(
        analyze_passage=AsyncMock(side_effect=RuntimeError("secret provider response"))))
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"accepted":True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://test") as api:
        await execute_task(api, {"id":str(uuid4()), "lease_id":str(uuid4()), "model":"fixture", "prompt_version":PROMPT_VERSION,
            "content":"source text", "source_name":"ECB", "title":"Title", "timeout_seconds":30}, "http://ollama", "fixture")
    assert calls[0]["error_code"] == "ollama_failed"
    assert "secret" not in json.dumps(calls)
