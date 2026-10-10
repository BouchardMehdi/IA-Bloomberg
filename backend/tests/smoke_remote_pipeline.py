"""End-to-end scheduler/queue/HTTP worker/fact persistence on disposable QA only."""
import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4
from unittest.mock import patch

import httpx
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.main import app
from app.models.article import Article
from app.models.event import Event
from app.models.source import Source
from app.repositories.events import EventRepository, PendingArticle
from app.schemas.semantic_analysis import PassageExtraction
from app.semantic.ollama import OllamaSemanticClient
from app.semantic.prompt import PROMPT_VERSION
from app.semantic.remote import RemoteSemanticClient
from app.services.remote_ai import RemoteAiService
from app.services.semantic_analysis import SemanticAnalysisService
from app.worker.main import execute_task
from tests.test_semantic_analysis import make_extraction


async def main():
    assert engine.url.database.endswith("_qa"), "Disposable QA database required"
    settings = get_settings()
    original = settings.model_copy(deep=True)
    stamp = uuid4().hex
    token = "fixture-" + stamp
    settings.ai_execution_mode, settings.ai_analysis_enabled = "remote", True
    settings.auth_enabled, settings.ollama_model = True, "fixture-" + stamp
    settings.ai_worker_token_sha256 = SecretStr(hashlib.sha256(token.encode()).hexdigest())
    quote = "The company approved an acquisition."
    extraction = PassageExtraction(events=[make_extraction(quote).model_dump()])
    try:
        # Offline scheduling retains one task; concurrent claims are disjoint,
        # including while the first claim's PostgreSQL transaction is still open.
        offline = RemoteSemanticClient(settings.ollama_model, 0)
        try:
            await offline.analyze_passage("Fixture", "Offline " + stamp, quote)
            raise AssertionError("Offline call should time out")
        except TimeoutError:
            pass
        async with async_session_factory() as session:
            await RemoteAiService(session).enqueue(settings.ollama_model, "Fixture", "Second " + stamp, quote)
            await session.commit()
        async with async_session_factory() as first, async_session_factory() as second:
            lease1 = await RemoteAiService(first).claim(settings.ollama_model, 30)
            lease2 = await RemoteAiService(second).claim(settings.ollama_model, 30)
            assert lease1 and lease2 and lease1["id"] != lease2["id"]
            await first.commit()
            await second.commit()
            await RemoteAiService(first).complete(lease1["id"], lease1["lease_id"], extraction)
            await first.commit()
            await RemoteAiService(second).complete(lease2["id"], lease2["lease_id"], extraction)
            await second.commit()
        cached = await offline.analyze_passage("Fixture", "Offline " + stamp, quote)
        assert cached.extraction == extraction

        async with async_session_factory() as session:
            source = Source(name="Remote pipeline " + stamp, source_type="central_bank",
                url="https://www.ecb.europa.eu", reliability_score=1, enabled=True)
            session.add(source)
            await session.flush()
            article = Article(source_id=source.id, title="Acquisition", content=quote, full_content=quote,
                content_status="success", url=f"https://www.ecb.europa.eu/press/{stamp}.html",
                published_at=datetime.now(UTC), fetched_at=datetime.now(UTC), content_hash=stamp,
                content_truncated=False)
            session.add(article)
            await session.flush()
            await EventRepository(session).add_from_article(PendingArticle(article, source))
            await session.commit()
            source_name = source.name
            parent_id = (await session.execute(select(Event.id).where(
                Event.deduplication_key == f"primary-article:{article.id}"))).scalar_one()
        inference_calls = []
        def ollama(request):
            inference_calls.append(request)
            return httpx.Response(200, json={"message":{"content":extraction.model_dump_json()}})
        done = asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.MockTransport(ollama), base_url="http://ollama") as simulated:
            def client(*args, **kwargs):
                return OllamaSemanticClient("http://ollama", settings.ollama_model, client=simulated)
            async def worker():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                    base_url="https://test/api/v1/ai-worker", headers={"Authorization":f"Bearer {token}"}) as api:
                    while not done.is_set():
                        response = await api.post("/claim", json={"model":settings.ollama_model, "prompt_version":PROMPT_VERSION})
                        assert response.status_code == 200
                        if response.json()["task"]:
                            with patch("app.worker.main.OllamaSemanticClient", client):
                                await execute_task(api, response.json()["task"], "http://ollama", settings.ollama_model)
                        await asyncio.sleep(0.1)
            background = asyncio.create_task(worker())
            try:
                async with async_session_factory() as session:
                    service = SemanticAnalysisService(session, RemoteSemanticClient(settings.ollama_model, 60))
                    stats = await service.process_pending(1, source_name)
                    assert stats.succeeded == 1 and stats.facts_created == 1, stats
                    again = await service.process_pending(1, source_name)
                    assert again.succeeded == 0 and len(inference_calls) == 1
                    count = (await session.execute(select(func.count()).select_from(Event).where(
                        Event.parent_event_id == parent_id))).scalar_one()
                    assert count == 1
            finally:
                done.set()
                await background
        print("Full remote pipeline passed: offline retention/cache, concurrent claims, scheduler to HTTP worker to sourced child fact, no duplicate inference.")
    finally:
        for name in ("ai_execution_mode", "ai_analysis_enabled", "auth_enabled", "ollama_model", "ai_worker_token_sha256"):
            setattr(settings, name, getattr(original, name))


if __name__ == "__main__":
    asyncio.run(main())
