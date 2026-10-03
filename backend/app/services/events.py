from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.events import EventRepository
from app.schemas.event import (
    EventCompanyRead,
    EventPage,
    EventRead,
    EventSourceRead,
    SemanticAnalysisRead,
)


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = EventRepository(session)

    async def analysis_detail(self, event_id) -> dict | None:
        return await self.repository.analysis_detail(event_id)

    async def list_latest(self, limit: int, offset: int) -> EventPage:
        records, total = await self.repository.list_latest(limit=limit, offset=offset)
        return EventPage(
            items=[self._to_read(record) for record in records],
            total=total,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def _to_read(record) -> EventRead:
        successful_run = record.event.fact_analysis_run or next(
            (
                run
                for run in record.event.analysis_runs
                if run.coverage is not None
                or (run.status in {"success", "partial"} and run.result is not None)
            ),
            None,
        )
        semantic_analysis = None
        if successful_run is not None:
            semantic_analysis = SemanticAnalysisRead(
                model_name=successful_run.model_name,
                prompt_version=successful_run.prompt_version,
                duration_ms=successful_run.duration_ms,
                prompt_tokens=successful_run.prompt_tokens,
                completion_tokens=successful_run.completion_tokens,
                result=(record.event.structured_data or {}).get(
                    "fact", successful_run.result or {}
                ),
                source_url=successful_run.source_url,
                id=successful_run.id,
                status=successful_run.status,
                coverage=successful_run.coverage,
            )
        return EventRead(
            id=record.event.id,
            event_type=record.event.event_type,
            title=record.event.title,
            description=record.event.description,
            event_datetime=record.event.event_datetime,
            status=record.event.status,
            extraction_method=record.event.extraction_method,
            extraction_version=record.event.extraction_version,
            evidence_excerpt=record.event.evidence_excerpt,
            structured_data=record.event.structured_data,
            confidence_score=record.event.confidence_score,
            country=record.event.country,
            region=record.event.region,
            source_name=record.source_name,
            article_url=record.article_url,
            companies=[
                EventCompanyRead(
                    id=link.company.id,
                    cik=link.company.cik,
                    name=link.company.name,
                    role=link.role,
                )
                for link in record.event.company_links
            ],
            semantic_analysis=semantic_analysis,
            parent_event_id=record.event.parent_event_id,
            sources=[
                EventSourceRead(
                    article_id=link.article.id,
                    source_name=link.article.source.name,
                    url=link.article.url,
                    document_url=link.article.document_url,
                    published_at=link.article.published_at,
                    content_status=link.article.content_status,
                    is_primary_source=link.is_primary_source,
                )
                for link in record.event.article_links
            ],
        )
