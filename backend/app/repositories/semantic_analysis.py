import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_run import AnalysisRun
from app.models.article import Article
from app.models.event import Event, EventArticle
from app.models.source import Source
from app.schemas.semantic_analysis import SemanticExtraction

ANALYSIS_CHAR_LIMIT = 8000


def analysis_content(article: Article) -> str:
    return (article.full_content or article.content or "")[:ANALYSIS_CHAR_LIMIT]


@dataclass(frozen=True)
class AnalysisCandidate:
    event: Event
    article: Article
    source_name: str

    @property
    def input_hash(self) -> str:
        value = f"{self.article.title}\n{analysis_content(self.article)}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SemanticAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_candidates(
        self,
        model_name: str,
        prompt_version: str,
        limit: int,
        require_document: bool = True,
        source_name: str | None = None,
    ) -> list[AnalysisCandidate]:
        completed_run = AnalysisRun.__table__.alias("completed_run")
        ranked_sources = (
            select(
                EventArticle.event_id,
                EventArticle.article_id,
                func.row_number()
                .over(
                    partition_by=EventArticle.event_id,
                    order_by=[
                        Article.full_content.is_not(None).desc(),
                        EventArticle.is_primary_source.desc(),
                        Article.id,
                    ],
                )
                .label("position"),
            )
            .join(Article, Article.id == EventArticle.article_id)
            .subquery()
        )
        text = func.substr(
            func.coalesce(Article.full_content, Article.content, ""), 1, ANALYSIS_CHAR_LIMIT
        )
        input_hash = func.encode(
            func.sha256(func.convert_to(func.concat(Article.title, "\n", text), "UTF8")), "hex"
        )
        statement = (
            select(Event, Article, Source.name)
            .join(ranked_sources, ranked_sources.c.event_id == Event.id)
            .join(Article, Article.id == ranked_sources.c.article_id)
            .join(Source, Source.id == Article.source_id)
            .outerjoin(
                completed_run,
                and_(
                    completed_run.c.event_id == Event.id,
                    completed_run.c.model_name == model_name,
                    completed_run.c.prompt_version == prompt_version,
                    completed_run.c.input_hash == input_hash,
                    or_(
                        completed_run.c.status == "success",
                        and_(
                            completed_run.c.status == "failed",
                            completed_run.c.finished_at > datetime.now(UTC) - timedelta(minutes=10),
                        ),
                        and_(
                            completed_run.c.status == "running",
                            completed_run.c.started_at > datetime.now(UTC) - timedelta(minutes=31),
                        ),
                    ),
                ),
            )
            .where(
                ranked_sources.c.position == 1,
                Event.extraction_version.is_not(None),
                completed_run.c.id.is_(None),
                Event.merged_into_event_id.is_(None),
            )
            .order_by(Event.event_datetime.desc(), Event.id)
            .limit(limit)
        )
        if source_name is not None:
            statement = statement.where(Source.name == source_name)
        if require_document:
            statement = statement.where(
                or_(
                    Article.content_status.in_(["success", "unsupported"]),
                    and_(
                        Article.content_status == "failed", Article.content_next_retry_at.is_(None)
                    ),
                )
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
                input_text=f"{candidate.article.title}\n{analysis_content(candidate.article)}",
                source_url=candidate.article.document_url or candidate.article.url,
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
                    "result": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
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
    source_text = _normalize(f"{article.title}\n{analysis_content(article)}")
    missing = [
        item.quote for item in extraction.evidence if _normalize(item.quote) not in source_text
    ]
    if missing:
        raise ValueError(f"Evidence quote is absent from the source text: {missing[0][:200]}")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
