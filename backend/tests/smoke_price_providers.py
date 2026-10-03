"""Common price collection in PostgreSQL; fixture data always rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.providers import MarketDataError, ProviderPolicy, QuoteBatch
from app.models.market import DailyPrice, MarketFetchRun, MarketInstrument
from app.services.market_data import MarketDataService


class FixtureProvider:
    def __init__(self, provider, budget=10):
        self.policy = ProviderPolicy(provider=provider, daily_request_budget=budget)
        self.calls = []
        self.fault = None

    def supports(self, identity):
        return identity.exchange == "XHKG" and identity.currency == "HKD"

    async def fetch(self, identity):
        self.calls.append(identity)
        if self.fault == "quota":
            raise MarketDataError("provider_quota")
        if self.fault == "unexpected":
            raise RuntimeError("Never persist fixture-secret")
        batch = QuoteBatch(
            identity=identity,
            provider=self.policy.provider,
            provider_symbol="explicit-fixture-only:" + identity.symbol,
            source_url="https://example.org/price-fixture",
            records=[
                {
                    "session_date": datetime.now(UTC).date() - timedelta(days=1),
                    "close": "100",
                    "volume": 1000,
                },
                {"session_date": datetime.now(UTC).date(), "close": "101", "volume": 1001},
            ],
        )
        if self.fault == "invalid":
            # A bad last record must not leave a partial first-row update.
            last = batch.records[-1].model_copy(update={"close": Decimal("-1")})
            return batch.model_copy(
                update={
                    "records": (batch.records[0].model_copy(update={"close": Decimal("999")}), last)
                }
            )
        return batch


async def main():
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                suffix = uuid4().hex[:10]
                first = FixtureProvider("fixture_a_" + suffix, budget=1)
                second = FixtureProvider("fixture_b_" + suffix)
                instruments = []
                for provider in (first, first, second, second):
                    instrument = MarketInstrument(
                        symbol="FIX" + uuid4().hex[:8].upper(),
                        exchange="XHKG",
                        name="Fixture only",
                        currency="HKD",
                        quote_multiplier=Decimal("1"),
                        price_provider=provider.policy.provider,
                        registry_url="https://example.org/fixture",
                        registry_observed_at=datetime.now(UTC),
                    )
                    session.add(instrument)
                    await session.commit()
                    instruments.append(instrument)
                service = MarketDataService(session)
                stats = await service.collect(first)
                assert stats["success"] == 1 and stats["budget_exhausted"] and len(first.calls) == 1
                assert (await MarketDataService(session).collect(first))["budget_exhausted"]
                assert len(first.calls) == 1, "Quota persists across service instances"
                stats = await service.collect(second)
                assert stats["success"] == 2 and len(second.calls) == 2, "Quotas are independent"
                target = instruments[2]
                quote = await service.latest_price(target.id)
                assert (
                    quote.provider == second.policy.provider
                    and quote.quote_context["currency"] == "HKD"
                )
                assert quote.quote_context["exchange"] == "XHKG" and quote.close == Decimal("101")
                await service.collect(second)
                assert len(second.calls) == 2, "Daily success cache avoids another call"

                async def expire_runs():
                    runs = (
                        (
                            await session.execute(
                                select(MarketFetchRun).where(
                                    MarketFetchRun.provider == second.policy.provider
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for run in runs:
                        run.started_at = datetime.now(UTC) - timedelta(days=2)
                        run.retry_at = None
                    await session.commit()

                await expire_runs()
                second.fault = "invalid"
                stats = await service.collect(second, limit=1)
                assert stats["failed"] == 1
                prices = (
                    (
                        await session.execute(
                            select(DailyPrice).where(DailyPrice.instrument_id == target.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                assert sorted(p.close for p in prices) == [Decimal("100"), Decimal("101")]
                failed = (
                    await session.execute(
                        select(MarketFetchRun).where(
                            MarketFetchRun.provider == second.policy.provider,
                            MarketFetchRun.status == "failed",
                        )
                    )
                ).scalar_one()
                assert (
                    failed.error_code == "invalid_quote_batch"
                    and failed.retry_at > datetime.now(UTC)
                )
                # Make the other title cached, so the failing title alone is considered.
                other_run = (
                    await session.execute(
                        select(MarketFetchRun).where(
                            MarketFetchRun.instrument_id
                            == next(i.id for i in instruments[2:] if i.id != failed.instrument_id)
                        )
                    )
                ).scalar_one()
                other_run.started_at = datetime.now(UTC)
                await session.commit()
                before = len(second.calls)
                await service.collect(second)
                assert len(second.calls) == before, (
                    "Retry delay prevents immediate failed-title calls"
                )

                await expire_runs()
                second.fault = "quota"
                stats = await service.collect(second)
                assert stats["failed"] == 1 and stats["blocked_until"] is not None
                before = len(second.calls)
                await service.collect(second)
                assert len(second.calls) == before, (
                    "Provider quota blocks every title until next UTC day"
                )
                await expire_runs()
                second.fault = "unexpected"
                assert (await service.collect(second, limit=1))["failed"] == 1
                latest = (
                    await session.execute(
                        select(MarketFetchRun)
                        .where(MarketFetchRun.provider == second.policy.provider)
                        .order_by(MarketFetchRun.started_at.desc())
                        .limit(1)
                    )
                ).scalar_one()
                assert (
                    latest.error_code == "provider_internal_error"
                    and "fixture-secret" not in str(latest.quote_context)
                )
                assert (
                    await session.execute(
                        select(func.count())
                        .select_from(DailyPrice)
                        .where(DailyPrice.instrument_id.in_([i.id for i in instruments]))
                    )
                ).scalar_one() == 6

                async def fixture_session():
                    yield session

                app.dependency_overrides[get_db_session] = fixture_session
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as http:
                        data = (await http.get("/api/v1/market/price-collection")).json()
                        assert (
                            data["quota_timezone"] == "UTC"
                            and not data["international_quotes_connected"]
                        )
                        history = (
                            await http.get(f"/api/v1/market/instruments/{target.id}/prices")
                        ).json()
                        assert (
                            history["currency"] == "HKD"
                            and history["items"][0]["provider"] == second.policy.provider
                        )
                        assert "fixture-secret" not in str(history)
                finally:
                    app.dependency_overrides.pop(get_db_session, None)
                print(
                    "PostgreSQL price-provider smoke passed: independent quotas, cache, retry, "
                    "atomic validation, provenance and API"
                )
        finally:
            await outer.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
