"""Verify retry deadline migration without altering quota history; rolled back."""

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.models.market import MarketFetchRun, MarketInstrument


async def main():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            try:
                now = datetime.now(UTC)
                instrument = MarketInstrument(
                    symbol="RETRY" + uuid4().hex[:8],
                    exchange="NYSE",
                    currency="USD",
                    price_provider="manual",
                    name="Retry fixture",
                    registry_url="https://example.org/fixture",
                    registry_observed_at=now,
                )
                session.add(instrument)
                await session.flush()
                started = now - timedelta(minutes=10)
                finished = started + timedelta(seconds=5)
                runs = []
                for provider, status, error, finish in [
                    ("alpha_vantage", "failed", "provider_http_error", finished),
                    ("alpha_vantage", "failed", "provider_quota", finished),
                    ("alpha_vantage", "running", None, None),
                    ("fixture_other", "failed", "provider_http_error", finished),
                ]:
                    run = MarketFetchRun(
                        instrument_id=instrument.id,
                        provider=provider,
                        status=status,
                        error_code=error,
                        started_at=started,
                        finished_at=finish,
                        retry_at=now + timedelta(hours=1),
                    )
                    session.add(run)
                    runs.append(run)
                await session.flush()
                identifiers = [run.id for run in runs]
                path = Path("migrations/versions/20261004_0014_short_retry.py")
                spec = importlib.util.spec_from_file_location("retry_migration", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                statements = []
                module.op = SimpleNamespace(execute=statements.append)
                module.upgrade()
                for sql in statements:
                    await session.execute(text(sql))
                session.expire_all()
                saved = (
                    (
                        await session.execute(
                            select(MarketFetchRun).where(MarketFetchRun.id.in_(identifiers))
                        )
                    )
                    .scalars()
                    .all()
                )
                by_id = {run.id: run for run in saved}
                assert len(saved) == 4
                assert by_id[identifiers[0]].retry_at == finished + timedelta(minutes=5)
                for identifier in identifiers[1:]:
                    assert by_id[identifier].retry_at == now + timedelta(hours=1)
                assert all(run.started_at == started for run in saved)
                assert by_id[identifiers[1]].error_code == "provider_quota"
                print(
                    "Short-retry migration passed; quota history preserved; fixtures rolled back."
                )
            finally:
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
