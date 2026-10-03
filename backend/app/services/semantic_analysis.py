import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.semantic_analysis import (
    SemanticAnalysisRepository,
    analysis_content,
    validate_evidence,
)
from app.semantic.ollama import OllamaSemanticClient
from app.semantic.prompt import PROMPT_VERSION


@dataclass(frozen=True)
class SemanticAnalysisStats:
    succeeded: int
    failed: int


class SemanticAnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        client: OllamaSemanticClient,
        require_document: bool = True,
    ) -> None:
        self.session = session
        self.client = client
        self.require_document = require_document
        self.repository = SemanticAnalysisRepository(session)

    async def process_pending(
        self, limit: int = 5, source_name: str | None = None
    ) -> SemanticAnalysisStats:
        candidates = await self.repository.list_candidates(
            self.client.model,
            PROMPT_VERSION,
            limit,
            require_document=self.require_document,
            source_name=source_name,
        )
        succeeded = 0
        failed = 0
        for candidate in candidates:
            # A previous failed attempt rolls back and expires loaded ORM objects.
            await self.session.refresh(candidate.event)
            await self.session.refresh(candidate.article)
            run_id = await self.repository.start(
                candidate,
                self.client.model,
                PROMPT_VERSION,
            )
            await self.session.commit()
            started = time.perf_counter()
            try:
                result = await self.client.analyze(
                    candidate.source_name,
                    candidate.article.title,
                    analysis_content(candidate.article),
                )
                validate_evidence(result.extraction, candidate.article)
                duration_ms = round((time.perf_counter() - started) * 1000)
                await self.repository.succeed(
                    run_id,
                    candidate.event,
                    result.extraction,
                    duration_ms,
                    result.prompt_tokens,
                    result.completion_tokens,
                )
                await self.session.commit()
                succeeded += 1
            except Exception as error:
                await self.session.rollback()
                duration_ms = round((time.perf_counter() - started) * 1000)
                await self.repository.fail(
                    run_id,
                    duration_ms,
                    f"{type(error).__name__}: {error}",
                )
                await self.session.commit()
                failed += 1
        return SemanticAnalysisStats(succeeded=succeeded, failed=failed)
