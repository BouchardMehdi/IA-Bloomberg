"""PostgreSQL/API checks; all fixture records rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.earnings_calendar import EarningsCalendarClient
from app.market.providers import ProviderPolicy, QuoteBatch
from app.models.earnings import EarningsObservation
from app.models.market import MarketFetchRun, MarketInstrument
from app.services.earnings import EarningsService
from app.services.market_data import MarketDataService


class FixturePrices:
    policy = ProviderPolicy(provider="fixture_earnings", daily_request_budget=4)

    def supports(self, identity):
        return True

    async def fetch(self, identity):
        return QuoteBatch(
            identity=identity,
            provider=self.policy.provider,
            provider_symbol=identity.symbol,
            source_url="https://example.org/close",
            records=[{"session_date": datetime.now(UTC).date(), "close": "10", "volume": 1}],
        )


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
                today = datetime.now(UTC).date()
                instrument = MarketInstrument(
                    symbol="SMOKE" + uuid4().hex[:8],
                    exchange="NYSE",
                    currency="USD",
                    price_provider="alpha_vantage",
                    name="Fixture",
                    registry_url="https://example.org/registry",
                    registry_observed_at=datetime.now(UTC),
                )
                session.add(instrument)
                await session.commit()
                identifier = instrument.id
                other = MarketInstrument(
                    symbol="OTHER" + uuid4().hex[:8],
                    exchange="NYSE",
                    currency="USD",
                    price_provider="manual",
                    name="Other fixture",
                    registry_url="https://example.org/registry",
                    registry_observed_at=datetime.now(UTC),
                )
                session.add(other)
                await session.commit()
                calls = []

                def response(request):
                    calls.append(request)
                    return httpx.Response(
                        200,
                        text="symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
                        f"{instrument.symbol},Fixture,{today + timedelta(days=20)},"
                        f"{today - timedelta(days=10)},0,USD\n",
                    )

                client = EarningsCalendarClient(
                    "fixture-secret", transport=httpx.MockTransport(response)
                )
                client.policy = FixturePrices.policy
                # A price reservation counts against the same calendar quota.
                session.add(
                    MarketFetchRun(
                        instrument_id=other.id,
                        provider=client.policy.provider,
                        operation="prices",
                        status="failed",
                        started_at=datetime.now(UTC),
                    )
                )
                await session.commit()
                service = EarningsService(session)
                assert (await service.collect(identifier, client))["inserted"] == 2
                assert len(calls) == 1
                assert (await service.collect(identifier, client))[
                    "status"
                ] == "calendar_budget_exhausted"
                automatic = (await service.detail(identifier, 50, 0))["items"]
                assert len(automatic) == 2
                assert all(item["published_at"] is None for item in automatic)
                assert all("fixture-secret" not in item["source_url"] for item in automatic)
                assert next(item for item in automatic if item["kind"] == "estimate")["eps"] == "0"
                # Calendar freshness must never suppress the price request.
                instrument.price_provider = client.policy.provider
                await session.commit()
                assert (await MarketDataService(session).collect(FixturePrices()))["success"] == 1
                attempts = (
                    await session.execute(
                        select(func.count())
                        .select_from(MarketFetchRun)
                        .where(MarketFetchRun.provider == client.policy.provider)
                    )
                ).scalar_one()
                assert attempts == 3
                instrument.price_provider = "manual"
                await session.commit()
                assert (await service.collect(identifier, client))[
                    "status"
                ] == "unsupported_listing"
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as api:
                    path = f"/api/v1/market/instruments/{identifier}/earnings"
                    estimate = {
                        "kind": "estimate",
                        "fiscal_period_end": str(today - timedelta(days=30)),
                        "period_type": "quarterly",
                        "report_date": str(today),
                        "eps": "0",
                        "currency": "USD",
                        "basis": "gaap_diluted",
                        "source_url": "https://example.org/estimate",
                        "published_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                    }
                    saved = await api.post(path, json=estimate)
                    assert saved.status_code == 201 and saved.json()["inserted"]
                    duplicate = await api.post(path, json=estimate)
                    assert duplicate.status_code == 201 and not duplicate.json()["inserted"]
                    result = {
                        **estimate,
                        "kind": "reported",
                        "eps": "1",
                        "source_url": "https://example.org/results",
                        "published_at": datetime.now(UTC).isoformat(),
                    }
                    assert (await api.post(path, json=result)).status_code == 201
                    data = (await api.get(path)).json()
                    reported = next(item for item in data["items"] if item["kind"] == "reported")
                    assert reported["comparison"]["status"] == "comparable"
                    assert reported["comparison"]["delta"] == "1"
                    assert reported["comparison"]["percent"] is None
                    assert data["collection"]["supported"] is False
                    assert (await api.get(path + "?limit=0")).status_code == 422
                    invalid = {**result, "source_url": "https://example.org/?apikey=secret"}
                    assert (await api.post(path, json=invalid)).status_code == 422
                    assert (
                        await api.get(f"/api/v1/market/instruments/{uuid4()}/earnings")
                    ).status_code == 404
                assert (
                    await session.execute(
                        select(func.count())
                        .select_from(EarningsObservation)
                        .where(EarningsObservation.instrument_id == identifier)
                    )
                ).scalar_one() == 4
                instrument.price_provider = "alpha_vantage"
                await session.commit()
                failed = EarningsCalendarClient(
                    "fixture-secret",
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, json={"Note": "fixture-secret"})
                    ),
                )
                failed.policy = ProviderPolicy(
                    provider="fixture_earnings_failed", daily_request_budget=4
                )
                result = await service.collect(identifier, failed)
                assert result["status"] == "failed" and result["error_code"] == "provider_quota"
                assert (await service.collect(identifier, failed))["status"] == "provider_cooldown"
                assert len((await service.detail(identifier, 50, 0))["items"]) == 4
                print("Earnings PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
