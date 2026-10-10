"""Real PostgreSQL + worker HTTP contract, with simulated Ollama only; rollback all rows."""
import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import engine, get_db_session
from app.main import app
from app.models.ai_task import AiTask
from app.schemas.semantic_analysis import PassageExtraction
from app.semantic.ollama import OllamaSemanticClient
from app.semantic.prompt import PROMPT_VERSION
from app.services.remote_ai import RemoteAiService
from app.worker.main import execute_task
from tests.test_semantic_analysis import make_extraction


async def main():
    assert engine.url.database.endswith("_qa"), "Run only on the isolated QA database"
    settings = get_settings()
    original = settings.model_copy(deep=True)
    settings.ai_execution_mode = "remote"
    settings.ai_analysis_enabled = True
    settings.auth_enabled = True
    settings.ollama_model = "fixture-" + uuid4().hex
    token = "fixture-" + uuid4().hex
    from pydantic import SecretStr
    settings.ai_worker_token_sha256 = SecretStr(hashlib.sha256(token.encode()).hexdigest())
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as session:
                async def db():
                    yield session
                app.dependency_overrides[get_db_session] = db
                service = RemoteAiService(session)
                await service.heartbeat(settings.ollama_model)
                quote = "decided to keep rates unchanged"
                job = await service.enqueue(settings.ollama_model, "ECB", "Policy", quote)
                identifier = job.id
                await session.commit()
                again = await service.enqueue(settings.ollama_model, "ECB", "Policy", quote)
                assert again.id == identifier
                await session.commit()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test",
                    headers={"Authorization":f"Bearer {token}"}) as api:
                    # Bearer cannot become a web user; browser cookies cannot become a worker.
                    assert (await api.get("/api/v1/articles")).status_code == 401
                    assert (await api.post("/api/v1/ai-worker/claim", headers={"Authorization":"Bearer no"}, json={})).status_code == 401
                    claim = await api.post("/api/v1/ai-worker/claim", json={"model":settings.ollama_model, "prompt_version":PROMPT_VERSION})
                    assert claim.status_code == 200, claim.text
                    task = claim.json()["task"]
                    assert task["id"] == str(identifier)
                    # A second claimant cannot take an active lease.
                    assert await service.claim(settings.ollama_model, 30) is None
                    await session.commit()
                    invalid = PassageExtraction(events=[make_extraction("invented quote").model_dump()])
                    response = await api.post(f"/api/v1/ai-worker/{identifier}/complete", json={
                        "lease_id":task["lease_id"], "extraction":invalid.model_dump(mode="json")})
                    assert response.status_code == 409
                    extraction = PassageExtraction(events=[make_extraction(quote).model_dump()])
                    def ollama(request):
                        return httpx.Response(200, json={"message":{"content":extraction.model_dump_json()},
                            "prompt_eval_count":20, "eval_count":10})
                    async with httpx.AsyncClient(transport=httpx.MockTransport(ollama), base_url="http://ollama") as simulated:
                        def client(*args, **kwargs):
                            return OllamaSemanticClient("http://ollama", settings.ollama_model, client=simulated)
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test/api/v1/ai-worker",
                            headers={"Authorization":f"Bearer {token}"}) as worker_api:
                            with patch("app.worker.main.OllamaSemanticClient", client):
                                await execute_task(worker_api, task, "http://ollama", settings.ollama_model)
                    saved = await service.enqueue(settings.ollama_model, "ECB", "Policy", quote)
                    await session.refresh(saved)
                    assert saved.status == "success" and saved.result == extraction.model_dump(mode="json")
                    result = {"lease_id":task["lease_id"], "extraction":extraction.model_dump(mode="json")}
                    assert (await api.post(f"/api/v1/ai-worker/{identifier}/complete", json=result)).status_code == 200
                    result["extraction"] = {"events":[]}
                    assert (await api.post(f"/api/v1/ai-worker/{identifier}/complete", json=result)).status_code == 409
                    # Expiry, replacement and stale result rejection, then bounded errors.
                    second = await service.enqueue(settings.ollama_model, "ECB", "Policy2", quote)
                    second_id = second.id
                    await session.commit()
                    lease = await service.claim(settings.ollama_model, 30)
                    leased = await session.get(AiTask, second_id)
                    leased.lease_until = datetime.now(UTC) - timedelta(seconds=1)
                    await session.commit()
                    replacement = await service.claim(settings.ollama_model, 30)
                    await session.commit()
                    assert replacement["lease_id"] != lease["lease_id"]
                    try:
                        await service.complete(second_id, lease["lease_id"], extraction)
                        raise AssertionError("Old lease accepted")
                    except ValueError:
                        pass
                    await service.complete(second_id, replacement["lease_id"], None, error_code="ollama_failed")
                    await session.commit()
                    assert await service.claim(settings.ollama_model, 30) is None
                    leased = await session.get(AiTask, second_id)
                    leased.available_at = datetime.now(UTC) - timedelta(seconds=1)
                    await session.commit()
                    third = await service.claim(settings.ollama_model, 30)
                    await service.complete(second_id, third["lease_id"], None, error_code="ollama_failed")
                    await session.commit()
                    assert leased.status == "failed" and leased.attempts == 3
                    assert await service.claim(settings.ollama_model, 30) is None
                    summary = await api.get("/api/v1/workspace/ai-status")
                    assert summary.status_code == 401
                    state = await service.status(True, "remote")
                    assert state["worker_status"] == "recent" and state["counts"]["failed"] >= 1
                print("Remote AI verified: durable queue, scoped auth, worker execution, evidence rejection, idempotence, lease expiry and bounded retries.")
        finally:
            app.dependency_overrides.clear()
            for name in ("ai_execution_mode", "ai_analysis_enabled", "auth_enabled", "ollama_model", "ai_worker_token_sha256"):
                setattr(settings, name, getattr(original, name))
            await transaction.rollback()


if __name__ == "__main__":
    asyncio.run(main())
