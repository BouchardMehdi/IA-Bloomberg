import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_run import AnalysisRun
from app.models.article import Article
from app.models.event import Event, EventArticle
from app.models.source import Source
from app.schemas.semantic_analysis import SemanticExtraction


@dataclass(frozen=True)
class AnalysisCandidate:
    event: Event
    article: Article
    source_name: str

    @property
    def input_hash(self) -> str:
        value = f"{self.article.title}\n{self.article.content or ''}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SemanticAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_candidates(
        self,
        model_name: str,
        prompt_version: str,
        limit: int,
    ) -> list[AnalysisCandidate]:
        completed_run = AnalysisRun.__table__.alias("completed_run")
        statement = (
            select(Event, Article, Source.name)
            .join(EventArticle, EventArticle.event_id == Event.id)
            .join(Article, Article.id == EventArticle.article_id)
            .join(Source, Source.id == Article.source_id)
            .outerjoin(
                completed_run,
                and_(
                    completed_run.c.event_id == Event.id,
                    completed_run.c.model_name == model_name,
                    completed_run.c.prompt_version == prompt_version,
                    completed_run.c.status == "success",
                ),
            )
            .where(
                EventArticle.is_primary_source.is_(True),
                Event.extraction_version.is_not(None),
                completed_run.c.id.is_(None),
            )
            .order_by(Event.event_datetime.desc(), Event.id)
            .limit(limit)
        )
        rows = (await self.session.execute(statement)).all()
        return [AnalysisCandidate(event=row[0], article=row[1], source_name=row[2]) for row in rows]

    async def start(
        self,
        candidate: AnalysisCandidate,
        model_name: str,
        prompt_version: str,
    ) -> uuid.UUID:
        started_at = datetime.now(UTC)
        statement = (
            insert(AnalysisRun)
            .values(
                event_id=candidate.event.id,
                model_name=model_name,
                prompt_version=prompt_version,
                input_hash=candidate.input_hash,
                status="running",
                started_at=started_at,
            )
            .on_conflict_do_update(
                constraint="uq_analysis_runs_event_model_prompt",
                set_={
                    "input_hash": candidate.input_hash,
                    "status": "running",
                    "started_at": started_at,
                    "finished_at": None,
                    "duration_ms": None,
                    "error_message": None,
                },
            )
            .returning(AnalysisRun.id)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def succeed(
        self,
        run_id: uuid.UUID,
        event: Event,
        extraction: SemanticExtraction,
        duration_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        await self.session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(
                status="success",
                finished_at=datetime.now(UTC),
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                result=extraction.model_dump(mode="json"),
            )
        )
        event.event_type = extraction.event_type
        event.description = extraction.summary
        event.status = "analyzed"
        event.importance_score = extraction.importance_score
        event.urgency_score = extraction.urgency_score
        event.confidence_score = extraction.confidence_score
        event.sentiment_score = extraction.sentiment_score

    async def fail(self, run_id: uuid.UUID, duration_ms: int, error_message: str) -> None:
        await self.session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(
                status="failed",
                finished_at=datetime.now(UTC),
                duration_ms=duration_ms,
                error_message=error_message[:4000],
            )
        )


def validate_evidence(extraction: SemanticExtraction, article: Article) -> None:
    source_text = _normalize(f"{article.title}\n{article.content or ''}")
    missing = [
        item.quote for item in extraction.evidence if _normalize(item.quote) not in source_text
    ]
    if missing:
        raise ValueError("Evidence quote is absent from the source text")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
