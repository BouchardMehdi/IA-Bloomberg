import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.document_analysis import DocumentAnalysisRepository, validate_passage_evidence
from app.semantic.ollama import OllamaSemanticClient
from app.semantic.passages import PassagePlanner
from app.semantic.prompt import PROMPT_VERSION


@dataclass(frozen=True)
class SemanticAnalysisStats:
    succeeded: int
    failed: int
    partial: int = 0
    facts_created: int = 0


class SemanticAnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        client: OllamaSemanticClient,
        require_document: bool = True,
        planner: PassagePlanner | None = None,
    ) -> None:
        self.session = session
        self.client = client
        self.require_document = require_document
        settings = get_settings()
        self.planner = planner or PassagePlanner(
            settings.ai_passage_chars, settings.ai_max_passages, settings.ai_input_budget_chars
        )
        self.repository = DocumentAnalysisRepository(session)
        self.lease_seconds = (
            self.planner.max_passages * int(getattr(client, "timeout_seconds", 600)) + 120
        )

    async def process_pending(
        self, limit: int = 5, source_name: str | None = None
    ) -> SemanticAnalysisStats:
        candidates = await self.repository.list_candidates(
            self.client.model,
            PROMPT_VERSION,
            limit,
            require_document=self.require_document,
            source_name=source_name,
            planning_signature=self.planner.signature,
            lease_seconds=self.lease_seconds,
        )
        counts = {"success": 0, "failed": 0, "partial": 0}
        facts_created = 0
        for candidate in candidates:
            # A previous failed attempt rolls back and expires loaded ORM objects.
            await self.session.refresh(candidate.event)
            await self.session.refresh(candidate.article)
            text = (
                candidate.article.full_content
                or candidate.article.content
                or candidate.article.title
            )
            title = candidate.article.title
            plan = self.planner.plan(text)
            run_id = await self.repository.start(
                candidate,
                self.client.model,
                PROMPT_VERSION,
                lease_seconds=self.lease_seconds,
            )
            if run_id is None:
                await self.session.rollback()
                continue
            await self.repository.prepare(run_id, plan, candidate)
            records = {p.index: p for p in await self.repository.passages(run_id)}
            await self.session.commit()
            for passage in plan.selected:
                saved = records[passage.index]
                if saved.status == "success":
                    continue
                started = time.perf_counter()
                try:
                    result = await self.client.analyze_passage(
                        candidate.source_name, title, passage.text
                    )
                    validate_passage_evidence(result.extraction, title, passage.text)
                    created = await self.repository.save_success(
                        run_id,
                        saved,
                        passage,
                        candidate,
                        result.extraction,
                        round((time.perf_counter() - started) * 1000),
                        result.prompt_tokens,
                        result.completion_tokens,
                    )
                    await self.repository.prepare(run_id, plan, candidate)
                    await self.session.commit()
                    facts_created += created
                except Exception as error:
                    await self.session.rollback()
                    await self.session.refresh(candidate.event)
                    await self.session.refresh(candidate.article)
                    await self.repository.save_failure(
                        saved,
                        round((time.perf_counter() - started) * 1000),
                        f"{type(error).__name__}: {error}",
                    )
                    await self.repository.prepare(run_id, plan, candidate)
                    await self.session.commit()
            status, _ = await self.repository.finish(run_id, candidate, plan)
            await self.session.commit()
            counts[status] += 1
        return SemanticAnalysisStats(
            counts["success"], counts["failed"], counts["partial"], facts_created
        )
