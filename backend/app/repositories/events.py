import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis_passage import AnalysisPassage
from app.models.analysis_run import AnalysisRun
from app.models.article import Article
from app.models.company import Company, EventCompany
from app.models.event import Event, EventArticle
from app.models.source import Source

SEC_TITLE_PATTERN = re.compile(
    r"^(?P<form>(?:8-K|10-Q|10-K|6-K|20-F|40-F)(?:/A)?)\s+-\s+"
    r"(?P<company>.+?)\s+\((?P<cik>\d{10})\)\s+\([^)]+\)$"
)
ACCESSION_PATTERN = re.compile(r"accession-number=(?P<accession>[\d-]+)")
EXTRACTION_VERSION = "deterministic-v1"


@dataclass(frozen=True)
class PendingArticle:
    article: Article
    source: Source


@dataclass(frozen=True)
class PendingEvent:
    event: Event
    article: Article
    source: Source


@dataclass(frozen=True)
class EventRecord:
    event: Event
    source_name: str
    article_url: str


@dataclass(frozen=True)
class SECCompanyData:
    form: str
    name: str
    cik: str


def parse_sec_filing_title(title: str) -> SECCompanyData | None:
    match = SEC_TITLE_PATTERN.match(title.strip())
    if not match:
        return None
    return SECCompanyData(
        form=match.group("form"),
        name=match.group("company").strip(),
        cik=match.group("cik"),
    )


def _evidence_excerpt(article: Article) -> str:
    value = article.content or article.title
    return " ".join(value.split())[:500]


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def analysis_detail(self, event_id) -> dict | None:
        fact_run = select(Event.fact_analysis_run_id).where(Event.id == event_id).scalar_subquery()
        run = (
            await self.session.execute(
                select(AnalysisRun)
                .where((AnalysisRun.event_id == event_id) | (AnalysisRun.id == fact_run))
                .order_by(AnalysisRun.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        passages = (
            (
                await self.session.execute(
                    select(AnalysisPassage)
                    .where(AnalysisPassage.run_id == run.id)
                    .order_by(AnalysisPassage.passage_index)
                )
            )
            .scalars()
            .all()
        )
        return {
            "id": run.id,
            "status": run.status,
            "source_url": run.source_url,
            "model_name": run.model_name,
            "prompt_version": run.prompt_version,
            "coverage": run.coverage,
            "passages": [
                {
                    "index": p.passage_index,
                    "start": p.start_offset,
                    "end": p.end_offset,
                    "text": p.input_text,
                    "status": p.status,
                    "result": p.result,
                    "error_message": p.error_message,
                    "prompt_tokens": p.prompt_tokens,
                    "completion_tokens": p.completion_tokens,
                }
                for p in passages
            ],
        }

    async def lock_pending_articles(self, limit: int) -> list[PendingArticle]:
        statement = (
            select(Article, Source)
            .join(Source, Source.id == Article.source_id)
            .outerjoin(EventArticle, EventArticle.article_id == Article.id)
            .where(EventArticle.id.is_(None))
            .order_by(func.coalesce(Article.published_at, Article.fetched_at), Article.id)
            .limit(limit)
            .with_for_update(of=Article, skip_locked=True)
        )
        rows = (await self.session.execute(statement)).all()
        return [PendingArticle(article=row[0], source=row[1]) for row in rows]

    async def lock_unenriched_events(self, limit: int) -> list[PendingEvent]:
        statement = (
            select(Event, Article, Source)
            .join(EventArticle, EventArticle.event_id == Event.id)
            .join(Article, Article.id == EventArticle.article_id)
            .join(Source, Source.id == Article.source_id)
            .where(
                Event.extraction_version.is_(None),
                EventArticle.is_primary_source.is_(True),
            )
            .order_by(Event.created_at, Event.id)
            .limit(limit)
            .with_for_update(of=Event, skip_locked=True)
        )
        rows = (await self.session.execute(statement)).all()
        return [PendingEvent(event=row[0], article=row[1], source=row[2]) for row in rows]

    async def add_from_article(self, pending: PendingArticle) -> None:
        article = pending.article
        source = pending.source
        event_type = (
            "regulatory_filing"
            if source.source_type == "regulator"
            else "central_bank_announcement"
        )
        event = Event(
            deduplication_key=f"primary-article:{article.id}",
            event_type=event_type,
            title=article.title,
            description=article.content,
            event_datetime=article.published_at or article.fetched_at,
            event_time_type="published",
            status="detected",
            confidence_score=1.0,
            country=source.country,
            region=source.region,
        )
        event.article_links.append(
            EventArticle(
                article=article,
                is_primary_source=True,
                relevance_score=1.0,
            )
        )
        self.session.add(event)
        await self.session.flush()
        await self._apply_enrichment(event, article, source)

    async def enrich_event(self, pending: PendingEvent) -> None:
        await self._apply_enrichment(pending.event, pending.article, pending.source)

    async def _apply_enrichment(
        self,
        event: Event,
        article: Article,
        source: Source,
    ) -> None:
        event.extraction_method = "deterministic"
        event.extraction_version = EXTRACTION_VERSION
        event.evidence_excerpt = _evidence_excerpt(article)
        event.status = "enriched"

        if source.source_type != "regulator":
            event.structured_data = {
                "announcement_kind": "official_publication",
                "institution": source.name,
            }
            return

        company_data = parse_sec_filing_title(article.title)
        structured_data: dict[str, object] = {"form": "8-K"}
        if article.external_id:
            accession_match = ACCESSION_PATTERN.search(article.external_id)
            if accession_match:
                structured_data["accession_number"] = accession_match.group("accession")

        if company_data is None:
            event.structured_data = structured_data
            return

        structured_data.update(
            {
                "form": company_data.form,
                "company_name": company_data.name,
                "cik": company_data.cik,
            }
        )
        event.structured_data = structured_data
        company_id = (
            await self.session.execute(
                insert(Company)
                .values(cik=company_data.cik, name=company_data.name)
                .on_conflict_do_update(
                    index_elements=[Company.cik],
                    set_={"name": company_data.name, "updated_at": func.now()},
                )
                .returning(Company.id)
            )
        ).scalar_one()
        await self.session.execute(
            insert(EventCompany)
            .values(event_id=event.id, company_id=company_id, role="subject")
            .on_conflict_do_nothing()
        )

    async def list_latest(self, limit: int, offset: int) -> tuple[list[EventRecord], int]:
        statement = (
            select(Event, Source.name, Article.url)
            .options(
                selectinload(Event.company_links).joinedload(EventCompany.company),
                selectinload(Event.analysis_runs),
                selectinload(Event.fact_analysis_run),
                selectinload(Event.article_links)
                .joinedload(EventArticle.article)
                .joinedload(Article.source),
            )
            .join(EventArticle, EventArticle.event_id == Event.id)
            .join(Article, Article.id == EventArticle.article_id)
            .join(Source, Source.id == Article.source_id)
            .where(EventArticle.is_primary_source.is_(True), Event.merged_into_event_id.is_(None))
            .order_by(Event.event_datetime.desc(), Event.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(statement)).all()
        total = (
            await self.session.execute(
                select(func.count(Event.id)).where(Event.merged_into_event_id.is_(None))
            )
        ).scalar_one()
        return [
            EventRecord(event=row[0], source_name=row[1], article_url=row[2]) for row in rows
        ], total
