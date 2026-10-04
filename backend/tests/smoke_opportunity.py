"""Opportunity API/SQL checks with transaction rollback, no network collection."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.models.earnings import EarningsObservation
from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument


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
                    symbol="OPP" + uuid4().hex[:8],
                    exchange="NYSE",
                    cik=cik,
                    name="Opportunity fixture",
                    currency="USD",
                    price_provider="manual",
                    registry_url="https://example.org/identity",
                    registry_observed_at=now,
                )
                session.add(instrument)
                await session.flush()
                period = (now.date() - timedelta(days=30)).isoformat()
                filed = now.date().isoformat()
                for index, value in enumerate(["100", "-10"]):
                    session.add(
                        FinancialFact(
                            cik=cik,
                            fingerprint=uuid4().hex,
                            period_end=now.date(),
                            filed_on=now.date(),
                            observed_at=now,
                            data={
                                "metric": "net_income",
                                "value": value,
                                "unit": "USD",
                                "start": period,
                                "end": filed,
                                "filed": filed,
                                "concept": "NetIncomeLoss",
                                "accession": str(index),
                                "source_url": "https://example.org/filing",
                            },
                        )
                    )
                for provider, days in [("manual", 10), ("alpha_vantage", 12)]:
                    session.add(
                        EarningsObservation(
                            instrument_id=instrument.id,
                            fingerprint=uuid4().hex,
                            provider=provider,
                            observed_at=now,
                            data={
                                "kind": "schedule",
                                "fiscal_period_end": period,
                                "report_date": (now.date() + timedelta(days=days)).isoformat(),
                                "source_url": "https://example.org/calendar",
                                "published_at": None,
                            },
                        )
                    )
                await session.flush()
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    path = f"/api/v1/market/instruments/{instrument.id}/opportunity"
                    response = await client.get(path)
                    assert response.status_code == 200, response.text
                    body = response.json()
                    assert len(body["favorable"]) == len(body["risks"]) == 1
                    assert len(body["upcoming"]) == 2
                    assert all(item["conflicting_dates"] for item in body["upcoming"])
                    assert any("WLS" in item for item in body["missing_data"])
                    assert not body["coverage"]["limited"]
                    assert "score" not in body
                    assert body["favorable"][0]["value"] == "100"
                    assert (await client.get(path)).json()["favorable"] == body["favorable"]
                    instrument.cik = None
                    await session.flush()
                    empty = (await client.get(path)).json()
                    assert empty["favorable"] == empty["risks"] == []
                    assert (
                        await client.get(f"/api/v1/market/instruments/{uuid4()}/opportunity")
                    ).status_code == 404
                print("Opportunity PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
