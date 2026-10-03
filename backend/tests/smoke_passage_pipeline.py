"""Optional PostgreSQL smoke check; all fixture rows are rolled back.

Run: docker compose exec backend python -m tests.smoke_passage_pipeline
"""

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.models.analysis_passage import AnalysisPassage
from app.models.analysis_run import AnalysisRun
from app.models.article import Article
from app.models.event import Event
from app.models.source import Source
from app.repositories.events import EventRepository, PendingArticle
from app.semantic.ollama import OllamaSemanticClient
from app.semantic.passages import PassagePlanner
from app.services.event_grouping import EventGroupingService
from app.services.semantic_analysis import SemanticAnalysisService
from tests.test_semantic_analysis import make_extraction


async def main() -> None:
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                token = uuid.uuid4().hex
                source = Source(
                    name=f"Passage smoke {token}",
                    source_type="central_bank",
                    url="https://www.ecb.europa.eu",
                    reliability_score=1,
                    enabled=True,
                )
                session.add(source)
                await session.flush()
                acquisition = "The company approved an acquisition."
                dividend = "The company declared a dividend."
                text = (
                    "General historical context without new facts. " * 250
                    + " Item 1.01 "
                    + acquisition
                    + " Context only. " * 100
                    + " Item 8.01 "
                    + dividend
                )
                article = Article(
                    source_id=source.id,
                    url=f"https://www.ecb.europa.eu/press/{token}.en.html",
                    document_url=f"https://www.ecb.europa.eu/press/{token}.en.html",
                    title="Two distinct company announcements",
                    content="Official publication",
                    full_content=text,
                    full_content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    content_hash=hashlib.sha256(token.encode()).hexdigest(),
                    content_status="success",
                    published_at=datetime(2026, 10, 3, tzinfo=UTC),
                    fetched_at=datetime.now(UTC),
                    content_truncated=False,
                )
                session.add(article)
                await session.flush()
                await EventRepository(session).add_from_article(PendingArticle(article, source))
                await session.commit()
                parent = (
                    await session.execute(
                        select(Event).where(
                            Event.deduplication_key == f"primary-article:{article.id}"
                        )
                    )
                ).scalar_one()
                calls = []

                def handler(request: httpx.Request) -> httpx.Response:
                    passage = json.loads(request.content)["messages"][1]["content"]
                    calls.append(passage)
                    facts = []
                    for quote, summary in [
                        (acquisition, "La société a approuvé une acquisition."),
                        (dividend, "La société a annoncé un dividende."),
                    ]:
                        if quote in passage:
                            fact = make_extraction(quote)
                            fact.summary = summary
                            fact.event_type = "corporate_action"
                            fact.assets = []
                            facts.append(fact.model_dump(mode="json"))
                    return httpx.Response(
                        200,
                        json={
                            "message": {"content": json.dumps({"events": facts})},
                            "prompt_eval_count": 100,
                            "eval_count": 50,
                        },
                    )

                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handler), base_url="http://test"
                ) as http:
                    client = OllamaSemanticClient("http://test", "fixture-model", client=http)
                    planner = PassagePlanner(chunk_chars=800, max_passages=3, budget_chars=2400)
                    service = SemanticAnalysisService(session, client, planner=planner)
                    stats = await service.process_pending(1, source.name)
                    assert stats.succeeded == 1 and stats.facts_created == 2, stats
                    before = len(calls)
                    again = await service.process_pending(1, source.name)
                    assert again.succeeded == 0 and len(calls) == before
                await EventGroupingService(session).process()
                facts = (
                    (await session.execute(select(Event).where(Event.parent_event_id == parent.id)))
                    .scalars()
                    .all()
                )
                assert len(facts) == 2 and all(f.merged_into_event_id is None for f in facts)
                run = (
                    await session.execute(
                        select(AnalysisRun).where(AnalysisRun.event_id == parent.id)
                    )
                ).scalar_one()
                passages = (
                    (
                        await session.execute(
                            select(AnalysisPassage).where(AnalysisPassage.run_id == run.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert run.coverage["analyzed_count"] == 3 and run.coverage["coverage_ratio"] < 1
                assert sum(len(p.input_text) for p in passages) <= 2400
                assert all(text[p.start_offset : p.end_offset] == p.input_text for p in passages)
                print(
                    "PostgreSQL smoke passed: 2 distinct facts, 3 cached passages, "
                    "coverage and provenance preserved"
                )
        finally:
            await outer.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
