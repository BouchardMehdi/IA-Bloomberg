"""New SEC coverage, upgrade cache, instant persistence and dossier API; rollback."""

import asyncio
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.sec_financials import FinancialRecord
from app.models.collection_run import CollectionRun
from app.models.market import MarketInstrument
from app.models.source import Source
from app.services.financial_results import FinancialResultsService
from tests.smoke_financial_results import FixtureClient


class LiquidityClient(FixtureClient):
    async def fetch(self):
        rows = await super().fetch()
        today = datetime.now(UTC).date()
        for concept, metric, value, start in [
            ("CashAndCashEquivalentsAtCarryingValue", "cash", "500", None),
            ("LongTermDebtCurrent", "debt_current", "100", None),
            ("LongTermDebtNoncurrent", "debt_noncurrent", "200", None),
            (
                "NetCashProvidedByUsedInOperatingActivities",
                "operating_cash_flow",
                "-20",
                today - timedelta(days=100),
            ),
        ]:
            rows.append(
                FinancialRecord(
                    metric=metric,
                    concept=concept,
                    value=value,
                    unit="USD",
                    start=start,
                    end=today - timedelta(days=10),
                    filed=today - timedelta(days=1),
                    accession=f"{self.cik}-26-000002",
                    form="10-Q",
                )
            )
        return rows


async def main():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:

            async def override():
                yield session

            app.dependency_overrides[get_db_session] = override
            try:
                now = datetime.now(UTC)
                cik = str(int(uuid4().hex[:8], 16)).zfill(10)
                instrument = MarketInstrument(
                    symbol="LIQ" + uuid4().hex[:8],
                    exchange="NYSE",
                    cik=cik,
                    name="Liquidity fixture",
                    currency="USD",
                    price_provider="manual",
                    registry_url="https://example.org/identity",
                    registry_observed_at=now,
                )
                source = Source(
                    name=f"SEC financials {cik}",
                    source_type="regulator",
                    url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                )
                session.add_all([instrument, source])
                await session.flush()
                old = CollectionRun(
                    source_id=source.id,
                    trigger="manual",
                    status="success",
                    started_at=now,
                    finished_at=now,
                    collector_version=None,
                )
                session.add(old)
                await session.flush()
                fixture = LiquidityClient(cik)
                async with AsyncExitStack() as stack:
                    stack.enter_context(
                        patch(
                            "app.services.financial_results.SecFinancialClient",
                            return_value=fixture,
                        )
                    )
                    client = await stack.enter_async_context(
                        httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=app), base_url="http://test"
                        )
                    )
                    path = f"/api/v1/market/instruments/{instrument.id}"
                    # A v1 success permits one v2 collection, without deleting old run.
                    result = (await client.post(path + "/financials/collect")).json()
                    assert result["status"] == "success", result
                    assert result["inserted"] == 8
                    detail = (await client.get(path + "/financials")).json()
                    assert detail["collection"]["coverage_current"]
                    assert len([r for r in detail["items"] if r["period_type"] == "instant"]) == 3
                    assert all(
                        r["start"] is None for r in detail["items"] if r["period_type"] == "instant"
                    )
                    dossier = (await client.get(path + "/opportunity")).json()
                    assert len(dossier["liquidity"]) == 4
                    assert len(dossier["risks"]) == 2  # net loss and operating cash outflow
                    assert (await client.post(path + "/financials/collect")).json()[
                        "status"
                    ] == "cached_or_retry_pending"
                    assert fixture.calls == 1
                    run = await FinancialResultsService(session).latest(cik)
                    run.status = "failed"
                    run.collector_version = None
                    await session.flush()
                    assert (await client.post(path + "/financials/collect")).json()[
                        "status"
                    ] == "cached_or_retry_pending"
                    assert fixture.calls == 1
                print("Liquidity PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
