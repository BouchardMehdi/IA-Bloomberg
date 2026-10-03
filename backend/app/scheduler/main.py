import asyncio
import logging
import time
from collections.abc import Callable

from app.collectors.base import BaseCollector
from app.collectors.ecb import ECBPressCollector
from app.collectors.fed import FedPressCollector
from app.collectors.sec import SEC8KCollector
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.semantic.ollama import OllamaSemanticClient
from app.services.event_extraction import DeterministicEventExtractionService
from app.services.ingestion import ArticleIngestionService
from app.services.semantic_analysis import SemanticAnalysisService

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


def seconds_until_next_run(interval_minutes: int, elapsed_seconds: float) -> float:
    return max(1.0, interval_minutes * 60 - elapsed_seconds)


async def collect_once(name: str, collector: BaseCollector) -> None:
    async with async_session_factory() as session:
        stats = await ArticleIngestionService(session).run(
            collector,
            trigger="scheduled",
        )
    logger.info(
        "Scheduled %s collection completed: run_id=%s fetched=%s inserted=%s "
        "duplicates=%s duration_ms=%s",
        name,
        stats.run_id,
        stats.fetched,
        stats.inserted,
        stats.duplicates,
        stats.duration_ms,
    )


async def run_collector(
    name: str,
    collector_factory: Callable[[], BaseCollector],
    interval_minutes: int,
    run_on_start: bool,
) -> None:
    logger.info("%s scheduler started: interval_minutes=%s", name, interval_minutes)

    if not run_on_start:
        await asyncio.sleep(interval_minutes * 60)

    while True:
        cycle_started = time.monotonic()
        try:
            await collect_once(name, collector_factory())
        except Exception:
            logger.exception("Scheduled %s collection failed", name)

        delay = seconds_until_next_run(interval_minutes, time.monotonic() - cycle_started)
        logger.info("Next %s collection in %.1f seconds", name, delay)
        await asyncio.sleep(delay)


async def extract_events_once() -> None:
    async with async_session_factory() as session:
        stats = await DeterministicEventExtractionService(session).process_pending()
    logger.info(
        "Deterministic event extraction completed: created=%s enriched=%s",
        stats.created,
        stats.enriched,
    )


async def run_event_extractor(interval_minutes: int, run_on_start: bool) -> None:
    logger.info("Event extractor started: interval_minutes=%s", interval_minutes)
    if not run_on_start:
        await asyncio.sleep(interval_minutes * 60)

    while True:
        cycle_started = time.monotonic()
        try:
            await extract_events_once()
        except Exception:
            logger.exception("Deterministic event extraction failed")

        delay = seconds_until_next_run(interval_minutes, time.monotonic() - cycle_started)
        logger.info("Next event extraction in %.1f seconds", delay)
        await asyncio.sleep(delay)


async def analyze_events_once(client: OllamaSemanticClient, batch_size: int) -> None:
    async with async_session_factory() as session:
        stats = await SemanticAnalysisService(session, client).process_pending(batch_size)
    logger.info(
        "Semantic analysis completed: succeeded=%s failed=%s",
        stats.succeeded,
        stats.failed,
    )


async def run_semantic_analyzer(
    client: OllamaSemanticClient,
    interval_minutes: int,
    batch_size: int,
    run_on_start: bool,
) -> None:
    logger.info(
        "Semantic analyzer started: model=%s interval_minutes=%s batch_size=%s",
        client.model,
        interval_minutes,
        batch_size,
    )
    if not run_on_start:
        await asyncio.sleep(interval_minutes * 60)

    while True:
        cycle_started = time.monotonic()
        try:
            await analyze_events_once(client, batch_size)
        except Exception:
            logger.exception("Semantic analysis cycle failed")
        delay = seconds_until_next_run(interval_minutes, time.monotonic() - cycle_started)
        logger.info("Next semantic analysis in %.1f seconds", delay)
        await asyncio.sleep(delay)


async def serve() -> None:
    settings = get_settings()
    tasks = [
        run_collector(
            "ECB",
            ECBPressCollector,
            settings.ecb_collection_interval_minutes,
            settings.scheduler_run_on_start,
        ),
        run_collector(
            "Fed",
            FedPressCollector,
            settings.fed_collection_interval_minutes,
            settings.scheduler_run_on_start,
        ),
        run_collector(
            "SEC 8-K",
            lambda: SEC8KCollector(settings.sec_user_agent),
            settings.sec_collection_interval_minutes,
            settings.scheduler_run_on_start,
        ),
        run_event_extractor(
            settings.event_extraction_interval_minutes,
            settings.scheduler_run_on_start,
        ),
    ]
    if settings.ai_analysis_enabled:
        tasks.append(
            run_semantic_analyzer(
                OllamaSemanticClient(settings.ollama_base_url, settings.ollama_model),
                settings.ai_analysis_interval_minutes,
                settings.ai_analysis_batch_size,
                settings.scheduler_run_on_start,
            )
        )
    else:
        logger.info("Semantic analyzer disabled")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(serve())
