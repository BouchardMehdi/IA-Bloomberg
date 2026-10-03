import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.article import Article
from app.repositories.semantic_analysis import (
    ANALYSIS_CHAR_LIMIT,
    AnalysisCandidate,
    analysis_content,
    validate_evidence,
)
from app.schemas.semantic_analysis import EvidenceItem, PassageExtraction, SemanticExtraction
from app.semantic.ollama import OllamaSemanticClient
from app.services.semantic_analysis import SemanticAnalysisService


def make_extraction(quote: str) -> SemanticExtraction:
    return SemanticExtraction(
        summary="The central bank kept its policy rate unchanged.",
        event_type="monetary_policy",
        companies=[],
        assets=["policy rate"],
        dates=[],
        amounts=[],
        sentiment_score=0,
        importance_score=0.8,
        urgency_score=0.5,
        confidence_score=0.95,
        evidence=[EvidenceItem(claim="Rates were unchanged", quote=quote)],
    )


@pytest.mark.asyncio
async def test_ollama_client_requests_and_validates_structured_output() -> None:
    extraction = make_extraction("decided to keep rates unchanged")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["options"]["temperature"] == 0
        assert payload["format"]["type"] == "object"
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": extraction.model_dump_json()},
                "prompt_eval_count": 120,
                "eval_count": 45,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    ) as http_client:
        client = OllamaSemanticClient(
            "http://ollama.test",
            "qwen3:4b-instruct",
            client=http_client,
        )
        result = await client.analyze(
            "European Central Bank",
            "Monetary policy decisions",
            "The Governing Council decided to keep rates unchanged.",
        )

    assert result.extraction.event_type == "monetary_policy"
    assert result.prompt_tokens == 120
    assert result.completion_tokens == 45


def test_evidence_must_exist_in_the_source_text() -> None:
    article = Article(
        title="Monetary policy decisions",
        url="https://example.com",
        content="The Governing Council decided to keep rates unchanged.",
        source_id=None,
        fetched_at=datetime.now(UTC),
        content_hash="a" * 64,
    )

    validate_evidence(make_extraction("decided to keep rates unchanged"), article)

    with pytest.raises(ValueError, match="absent"):
        validate_evidence(make_extraction("rates were increased"), article)


def test_enriched_input_changes_hash_and_only_transmitted_quotes_are_valid() -> None:
    article = Article(title="Policy", content="decided to keep rates unchanged")
    candidate = AnalysisCandidate(event=None, article=article, source_name="ECB")
    rss_hash = candidate.input_hash
    article.full_content = "a" * ANALYSIS_CHAR_LIMIT + " decided to keep rates unchanged"
    assert candidate.input_hash != rss_hash
    assert len(analysis_content(article)) == ANALYSIS_CHAR_LIMIT
    with pytest.raises(ValueError, match="absent"):
        validate_evidence(make_extraction("decided to keep rates unchanged"), article)


@pytest.mark.asyncio
async def test_batch_continues_after_a_failed_analysis() -> None:
    article = Article(
        title="Rates unchanged",
        content="decided to keep rates unchanged",
    )
    candidates = [
        SimpleNamespace(event=object(), article=article, source_name="ECB") for _ in range(2)
    ]
    session = AsyncMock()
    client = SimpleNamespace(
        model="test-model",
        analyze_passage=AsyncMock(
            side_effect=[
                ValueError("invalid output"),
                SimpleNamespace(
                    extraction=PassageExtraction(
                        events=[make_extraction("decided to keep rates unchanged").model_dump()]
                    ),
                    prompt_tokens=120,
                    completion_tokens=45,
                ),
            ]
        ),
    )
    service = SemanticAnalysisService(session, client)
    service.repository = SimpleNamespace(
        list_candidates=AsyncMock(return_value=candidates),
        start=AsyncMock(side_effect=["first-run", "second-run"]),
        prepare=AsyncMock(),
        passages=AsyncMock(return_value=[SimpleNamespace(index=0, status="pending")]),
        save_failure=AsyncMock(),
        save_success=AsyncMock(return_value=1),
        finish=AsyncMock(side_effect=[("failed", 0), ("success", 1)]),
    )

    stats = await service.process_pending(2)

    assert (stats.succeeded, stats.failed) == (1, 1)
    session.rollback.assert_awaited_once()
    assert session.refresh.await_count == 6
    service.repository.save_failure.assert_awaited_once()
    service.repository.save_success.assert_awaited_once()
    assert stats.facts_created == 1
