import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.article import Article
from app.repositories.document_analysis import fact_key, validate_passage_evidence
from app.schemas.semantic_analysis import PassageExtraction
from app.semantic.ollama import OllamaSemanticClient
from app.semantic.passages import PassagePlanner
from app.services.semantic_analysis import SemanticAnalysisService
from tests.test_semantic_analysis import make_extraction


def test_late_material_fact_is_selected_beyond_the_old_prefix_limit() -> None:
    text = "General context without a financial fact. " * 240
    text += (
        " Item 1.01 Example entered into an acquisition agreement for $20 million. "
        "Revenue grew 10%."
    )
    plan = PassagePlanner(max_passages=1).plan(text)
    assert plan.selected[0].start > 8000
    assert "acquisition agreement" in plan.selected[0].text


def test_chunks_preserve_text_offsets_and_input_budget() -> None:
    text = "Sentence about context. " * 600
    plan = PassagePlanner(chunk_chars=1000, max_passages=5, budget_chars=2200).plan(text)
    assert "".join(p.text for p in plan.chunks) == text
    assert all(text[p.start : p.end] == p.text and len(p.text) <= 1000 for p in plan.chunks)
    assert sum(len(p.text) for p in plan.selected) <= 2200
    assert len(plan.selected) <= 5
    assert PassagePlanner(chunk_chars=1000, max_passages=5, budget_chars=2200).plan(text) == plan


def test_coverage_counts_only_successful_selected_passages() -> None:
    plan = PassagePlanner(chunk_chars=500, max_passages=2, budget_chars=1000).plan("Text. " * 600)
    statuses = {plan.selected[0].index: "success", plan.selected[1].index: "failed"}
    coverage = plan.coverage(statuses, truncated=True, source="document")
    assert coverage["analyzed_count"] == 1
    assert coverage["coverage_ratio"] == len(plan.selected[0].text) / len("Text. " * 600)
    assert coverage["document_truncated"]
    assert any(p["status"] == "not_selected" for p in coverage["passages"])


def test_signal_free_selection_samples_the_beginning_and_end() -> None:
    plan = PassagePlanner(chunk_chars=500, max_passages=3, budget_chars=1500).plan(
        "Context sentence. " * 250
    )
    assert plan.selected[0].index == 0
    assert plan.selected[-1].index == plan.chunks[-1].index


def test_quotes_from_untransmitted_sections_are_rejected_and_empty_results_are_allowed() -> None:
    result = PassageExtraction(
        events=[make_extraction("decided to keep rates unchanged").model_dump()]
    )
    validate_passage_evidence(result, "Policy", "The Council decided to keep rates unchanged.")
    with pytest.raises(ValueError, match="transmitted passage"):
        validate_passage_evidence(result, "Policy", "Another section of the same document.")
    validate_passage_evidence(PassageExtraction(events=[]), "Policy", "Boilerplate only")


def test_repeated_fact_with_reworded_summary_has_stable_identity() -> None:
    parent = uuid.uuid4()
    first = make_extraction("decided to keep rates unchanged")
    second = first.model_copy(deep=True, update={"summary": "Les taux restent inchangés."})
    assert fact_key(parent, first) == fact_key(parent, second)
    assert fact_key(parent, first) != fact_key(uuid.uuid4(), first)
    second.evidence[0] = second.evidence[0].model_copy(update={"quote": "increased rates"})
    assert fact_key(parent, first) != fact_key(parent, second)


@pytest.mark.asyncio
async def test_ollama_returns_multiple_facts_in_one_structured_passage() -> None:
    first = make_extraction("Rates unchanged")
    second = make_extraction("Approved acquisition")
    second.event_type = "corporate_action"
    output = PassageExtraction(events=[first.model_dump(), second.model_dump()])

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "events" in payload["format"]["properties"]
        assert "events" in payload["format"]["required"]
        assert payload["options"]["num_predict"] == 1536
        return httpx.Response(
            200,
            json={
                "message": {"content": output.model_dump_json()},
                "prompt_eval_count": 100,
                "eval_count": 90,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await OllamaSemanticClient("http://test", "test", client=client).analyze_passage(
            "Fed", "Official publication", "Rates unchanged. Approved acquisition."
        )
    assert len(result.extraction.events) == 2
    validate_passage_evidence(
        result.extraction, "Official publication", "Rates unchanged. Approved acquisition."
    )


@pytest.mark.asyncio
async def test_retry_reuses_successful_passage_and_keeps_partial_results() -> None:
    article = Article(title="Publication", content="Context sentence. " * 80)
    planner = PassagePlanner(chunk_chars=500, max_passages=2, budget_chars=1000)
    plan = planner.plan(article.content)
    candidate = SimpleNamespace(article=article, event=object(), source_name="Fed")
    client = SimpleNamespace(
        model="test", analyze_passage=AsyncMock(side_effect=ValueError("invalid quote"))
    )
    session = AsyncMock()
    service = SemanticAnalysisService(session, client, planner=planner)
    service.repository = SimpleNamespace(
        list_candidates=AsyncMock(return_value=[candidate]),
        start=AsyncMock(return_value="run"),
        prepare=AsyncMock(),
        passages=AsyncMock(
            return_value=[
                SimpleNamespace(index=plan.selected[0].index, status="success"),
                SimpleNamespace(index=plan.selected[1].index, status="failed"),
            ]
        ),
        save_success=AsyncMock(),
        save_failure=AsyncMock(),
        finish=AsyncMock(return_value=("partial", 1)),
    )
    stats = await service.process_pending(1)
    assert stats.partial == 1
    client.analyze_passage.assert_awaited_once()
    assert client.analyze_passage.call_args.args[2] == plan.selected[1].text
    service.repository.save_success.assert_not_awaited()
