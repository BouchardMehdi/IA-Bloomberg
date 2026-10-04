import asyncio
import logging
import time
from collections.abc import Callable

from app.collectors.base import BaseCollector
from app.collectors.documents import OfficialDocumentClient
from app.collectors.ecb import ECBPressCollector
from app.collectors.fed import FedPressCollector
from app.collectors.sec import SEC8KCollector
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.market.earnings_calendar import EarningsCalendarClient
from app.market.ecb_fx import EcbFxClient
from app.market.provider_registry import configured_price_providers
from app.semantic.ollama import OllamaSemanticClient
from app.services.document_content import DocumentContentService
from app.services.earnings import EarningsService
from app.services.entity_resolution import EntityResolutionService
from app.services.event_extraction import DeterministicEventExtractionService
from app.services.event_grouping import EventGroupingService
from app.services.fx_collection import FxCollectionService
from app.services.ingestion import ArticleIngestionService
from app.services.market_data import MarketDataService
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
        grouping = await EventGroupingService(session).process()
    logger.info("Event grouping completed: grouped=%s", grouping.grouped)
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
        stats = await SemanticAnalysisService(
            session, client, require_document=get_settings().document_collection_enabled
        ).process_pending(batch_size)
    logger.info(
        "Semantic analysis completed: succeeded=%s failed=%s partial=%s facts_created=%s",
        stats.succeeded,
        stats.failed,
        stats.partial,
        stats.facts_created,
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
        run_market_collector(),
        run_entity_resolver(),
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
    if settings.document_collection_enabled:
        tasks.append(run_document_fetcher())
    if settings.fx_collection_enabled:
        tasks.append(run_fx_collector())
    if settings.ai_analysis_enabled:
        tasks.append(
            run_semantic_analyzer(
                OllamaSemanticClient(
                    settings.ollama_base_url,
                    settings.ollama_model,
                    timeout_seconds=settings.ollama_timeout_seconds,
                ),
                settings.ai_analysis_interval_minutes,
                settings.ai_analysis_batch_size,
                settings.scheduler_run_on_start,
            )
        )
    else:
        logger.info("Semantic analyzer disabled")
    await asyncio.gather(*tasks)


async def run_document_fetcher() -> None:
    settings = get_settings()
    client = OfficialDocumentClient(
        settings.sec_user_agent, settings.document_max_bytes, settings.document_max_chars
    )
    if not settings.scheduler_run_on_start:
        await asyncio.sleep(settings.document_collection_interval_minutes * 60)
    while True:
        started = time.monotonic()
        try:
            async with async_session_factory() as session:
                stats = await DocumentContentService(session, client).process_pending(
                    settings.document_collection_batch_size
                )
            logger.info("Document retrieval completed: %s", stats)
        except Exception:
            logger.exception("Document retrieval cycle failed")
        await asyncio.sleep(
            seconds_until_next_run(
                settings.document_collection_interval_minutes, time.monotonic() - started
            )
        )


async def run_entity_resolver() -> None:
    settings = get_settings()
    if not settings.scheduler_run_on_start:
        await asyncio.sleep(60)
    next_sync = 0.0
    while True:
        started = time.monotonic()
        async with async_session_factory() as session:
            service = EntityResolutionService(session)
            if settings.entity_registry_enabled and started >= next_sync:
                try:
                    await service.sync_registry(settings.sec_user_agent)
                    next_sync = started + 3600
                except Exception:
                    await session.rollback()
                    next_sync = started + 3600
                    logger.exception(
                        "SEC identity registry refresh failed; keeping previous snapshot"
                    )
            try:
                count = await service.process_pending()
                logger.info("Entity resolution completed: processed=%s", count)
            except Exception:
                await session.rollback()
                logger.exception("Entity resolution failed")
        await asyncio.sleep(seconds_until_next_run(1, time.monotonic() - started))


async def run_market_collector() -> None:
    settings = get_settings()
    providers = configured_price_providers(settings)
    if not providers:
        logger.info("Market collection disabled: ALPHA_VANTAGE_API_KEY is not configured")
        return
    if not settings.scheduler_run_on_start:
        await asyncio.sleep(3600)
    while True:
        for provider in providers:
            try:
                async with async_session_factory() as session:
                    if (
                        settings.earnings_calendar_enabled
                        and provider.policy.provider == "alpha_vantage"
                    ):
                        await EarningsService(session).collect_scheduled(
                            EarningsCalendarClient(
                                settings.alpha_vantage_api_key.get_secret_value(),
                                daily_request_budget=settings.market_daily_request_budget,
                            )
                        )
                    stats = await MarketDataService(session).collect(provider)
                    logger.info("Market collection completed: %s", stats)
            except Exception:
                logger.exception("Market collection failed: %s", provider.policy.provider)
        await asyncio.sleep(3600)


async def run_fx_collector() -> None:
    settings = get_settings()
    interval = settings.fx_collection_interval_minutes
    if not settings.scheduler_run_on_start:
        await asyncio.sleep(interval * 60)
    client = EcbFxClient()
    while True:
        started = time.monotonic()
        try:
            async with async_session_factory() as session:
                stats = await FxCollectionService(session).collect(client)
                logger.info("ECB FX collection completed: %s", stats)
        except Exception:
            logger.exception("ECB FX collection failed; keeping previous rates")
        await asyncio.sleep(seconds_until_next_run(interval, time.monotonic() - started))


if __name__ == "__main__":
    asyncio.run(serve())
