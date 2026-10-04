"""SQL/API comparison guards and issuer isolation; fixtures always rolled back."""

import asyncio
from datetime import UTC, date, datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument
from tests.test_financial_trends import previous, row


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
                    symbol="TREND" + uuid4().hex[:8],
                    exchange="NYSE",
                    cik=cik,
                    name="Trend fixture",
                    currency="USD",
                    price_provider="manual",
                    registry_url="https://example.org/identity",
                    registry_observed_at=now,
                )
                session.add(instrument)
                await session.flush()

                async def add(data, identity=cik):
                    data = {k: v for k, v in data.items() if k != "id"}
                    session.add(
                        FinancialFact(
                            cik=identity,
                            fingerprint=uuid4().hex,
                            period_end=date.fromisoformat(data["end"]),
                            filed_on=date.fromisoformat(data["filed"]),
                            observed_at=now,
                            data=data,
                        )
                    )
                    await session.flush()

                await add(row())
                await add(previous())
                # Other issuer's contradictory observation must not leak into comparisons.
                await add(row(value="999"), str(int(cik) + 1).zfill(10))
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    path = f"/api/v1/market/instruments/{instrument.id}/financial-trends"
                    response = await client.get(path)
                    assert response.status_code == 200, response.text
                    result = response.json()
                    assert result["coverage"]["examined"] == 2
                    assert result["items"][0]["percent"] == "20.00"
                    assert result["items"][0]["delta"] == "20"
                    with patch("app.services.financial_trends.MAX_OBSERVATIONS", 1):
                        bounded = (await client.get(path)).json()
                        assert bounded["coverage"]["limited"]
                        assert bounded["items"] == []
                        assert bounded["reason"]
                    await add(previous(value="101"))
                    assert (await client.get(path)).json()["items"][0]["status"] == "not_comparable"
                    instrument.cik = None
                    await session.flush()
                    assert (await client.get(path)).json()["items"] == []
                    assert (
                        await client.get(f"/api/v1/market/instruments/{uuid4()}/financial-trends")
                    ).status_code == 404
                print("Financial trends PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
