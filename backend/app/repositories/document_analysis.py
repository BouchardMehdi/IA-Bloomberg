import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.models.analysis_passage import AnalysisPassage
from app.models.analysis_run import AnalysisRun
from app.models.company import EventCompany
from app.models.event import Event, EventArticle
from app.repositories.semantic_analysis import AnalysisCandidate, SemanticAnalysisRepository
from app.schemas.semantic_analysis import PassageExtraction, SemanticExtraction
from app.semantic.passages import Passage, PassagePlan


@dataclass(frozen=True)
class SavedPassage:
    id: uuid.UUID
    index: int
    status: str
    result: dict | None
    prompt_tokens: int | None
    completion_tokens: int | None
    duration_ms: int | None


def fact_key(parent_id: uuid.UUID, fact: SemanticExtraction) -> str:
    quotes = sorted(re.sub(r"\s+", " ", e.quote).strip().casefold() for e in fact.evidence)
    digest = hashlib.sha256(f"{fact.event_type}\n{'|'.join(quotes)}".encode()).hexdigest()
    return f"fact:{parent_id}:{digest}"


class DocumentAnalysisRepository(SemanticAnalysisRepository):
    async def prepare(
        self, run_id: uuid.UUID, plan: PassagePlan, candidate: AnalysisCandidate
    ) -> None:
        for p in plan.selected:
            await self.session.execute(
                insert(AnalysisPassage)
                .values(
                    run_id=run_id,
                    passage_index=p.index,
                    start_offset=p.start,
                    end_offset=p.end,
                    input_text=p.text,
                    input_hash=p.input_hash,
                    status="pending",
                )
                .on_conflict_do_nothing(constraint="uq_analysis_passages_run_index")
            )
        statuses = {p.index: p.status for p in await self.passages(run_id)}
        await self.session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(
                coverage=plan.coverage(
                    statuses,
                    truncated=bool(candidate.article.content_truncated),
                    source="document" if candidate.article.full_content else "rss",
                )
            )
        )

    async def passages(self, run_id: uuid.UUID) -> list[SavedPassage]:
        records = (
            (
                await self.session.execute(
                    select(AnalysisPassage)
                    .where(AnalysisPassage.run_id == run_id)
                    .order_by(AnalysisPassage.passage_index)
                )
            )
            .scalars()
            .all()
        )
        return [
            SavedPassage(
                p.id,
                p.passage_index,
                p.status,
                p.result,
                p.prompt_tokens,
                p.completion_tokens,
                p.duration_ms,
            )
            for p in records
        ]

    async def save_success(
        self,
        run_id: uuid.UUID,
        saved: SavedPassage,
        passage: Passage,
        candidate: AnalysisCandidate,
        result: PassageExtraction,
        duration_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> int:
        created = 0
        for fact in result.events:
            created += await self._save_fact(run_id, passage, candidate, fact)
        await self.session.execute(
            update(AnalysisPassage)
            .where(AnalysisPassage.id == saved.id)
            .values(
                status="success",
                result=result.model_dump(mode="json"),
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                finished_at=datetime.now(UTC),
                error_message=None,
            )
        )
        return created

    async def _save_fact(
        self,
        run_id: uuid.UUID,
        passage: Passage,
        candidate: AnalysisCandidate,
        fact: SemanticExtraction,
    ) -> int:
        parent = candidate.event
        key = fact_key(parent.id, fact)
        existing = (
            await self.session.execute(select(Event.id).where(Event.deduplication_key == key))
        ).scalar_one_or_none()
        values = dict(
            parent_event_id=parent.id,
            fact_analysis_run_id=run_id,
            event_type=fact.event_type,
            title=fact.summary[:200],
            description=fact.summary,
            event_datetime=candidate.article.published_at or parent.event_datetime,
            event_time_type="published",
            status="analyzed",
            extraction_method="ollama",
            extraction_version="semantic-v5-passages",
            evidence_excerpt=fact.evidence[0].quote,
            structured_data={
                "fact": fact.model_dump(mode="json"),
                "passage_index": passage.index,
                "start_offset": passage.start,
                "end_offset": passage.end,
            },
            country=parent.country,
            region=parent.region,
            confidence_score=fact.confidence_score,
            importance_score=fact.importance_score,
            urgency_score=fact.urgency_score,
            sentiment_score=fact.sentiment_score,
        )
        fact_id = (
            await self.session.execute(
                insert(Event)
                .values(deduplication_key=key, **values)
                .on_conflict_do_update(index_elements=[Event.deduplication_key], set_=values)
                .returning(Event.id)
            )
        ).scalar_one()
        article_ids = (
            (
                await self.session.execute(
                    select(EventArticle.article_id).where(EventArticle.event_id == parent.id)
                )
            )
            .scalars()
            .all()
        )
        for article_id in article_ids:
            await self.session.execute(
                insert(EventArticle)
                .values(
                    event_id=fact_id,
                    article_id=article_id,
                    is_primary_source=article_id == candidate.article.id,
                    relevance_score=1.0,
                )
                .on_conflict_do_update(
                    index_elements=[EventArticle.event_id, EventArticle.article_id],
                    set_={"is_primary_source": article_id == candidate.article.id},
                )
            )
        companies = (
            (
                await self.session.execute(
                    select(EventCompany.company_id).where(EventCompany.event_id == parent.id)
                )
            )
            .scalars()
            .all()
        )
        for company_id in companies:
            await self.session.execute(
                insert(EventCompany)
                .values(
                    event_id=fact_id,
                    company_id=company_id,
                    role="source_subject",
                )
                .on_conflict_do_nothing()
            )
        return int(existing is None)

    async def save_failure(self, saved: SavedPassage, duration_ms: int, error: str) -> None:
        await self.session.execute(
            update(AnalysisPassage)
            .where(AnalysisPassage.id == saved.id)
            .values(
                status="failed",
                duration_ms=duration_ms,
                error_message=error[:2000],
                finished_at=datetime.now(UTC),
            )
        )

    async def finish(
        self, run_id: uuid.UUID, candidate: AnalysisCandidate, plan: PassagePlan
    ) -> tuple[str, int]:
        records = await self.passages(run_id)
        statuses = {p.index: p.status for p in records}
        coverage = plan.coverage(
            statuses,
            truncated=bool(candidate.article.content_truncated),
            source="document" if candidate.article.full_content else "rss",
        )
        results = [p.result for p in records if p.status == "success" and p.result is not None]
        facts = [fact for result in results for fact in result["events"]]
        unique = {
            fact_key(candidate.event.id, SemanticExtraction.model_validate(f)): f for f in facts
        }
        facts = list(unique.values())
        success_count = sum(p.status == "success" for p in records)
        status = (
            "success" if success_count == len(records) else "partial" if success_count else "failed"
        )
        summary = " ".join(f["summary"] for f in facts)[:1500]
        result = {
            "summary": summary,
            "events": facts,
            "evidence": [e for f in facts for e in f["evidence"]],
        }
        await self.session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(
                status=status,
                finished_at=datetime.now(UTC),
                coverage=coverage,
                result=result if success_count else None,
                duration_ms=sum(p.duration_ms or 0 for p in records),
                prompt_tokens=(
                    sum(p.prompt_tokens or 0 for p in records)
                    if any(p.prompt_tokens is not None for p in records)
                    else None
                ),
                completion_tokens=(
                    sum(p.completion_tokens or 0 for p in records)
                    if any(p.completion_tokens is not None for p in records)
                    else None
                ),
                error_message=None
                if status == "success"
                else "One or more selected passages failed",
            )
        )
        candidate.event.status = (
            "analyzed"
            if status == "success"
            else "partially_analyzed"
            if success_count
            else "enriched"
        )
        if summary:
            candidate.event.description = summary
        else:
            candidate.event.description = candidate.article.content
        candidate.event.event_type = (
            "regulatory_filing"
            if (candidate.event.structured_data or {}).get("form")
            else "central_bank_announcement"
        )
        candidate.event.confidence_score = 1.0
        candidate.event.importance_score = None
        candidate.event.urgency_score = None
        candidate.event.sentiment_score = None
        return status, len(facts)


def validate_passage_evidence(result: PassageExtraction, title: str, passage: str) -> None:
    source = re.sub(r"\s+", " ", f"{title}\n{passage}").strip().casefold()
    for fact in result.events:
        for item in fact.evidence:
            quote = re.sub(r"\s+", " ", item.quote).strip().casefold()
            if quote not in source:
                raise ValueError("Evidence quote is absent from the transmitted passage")
