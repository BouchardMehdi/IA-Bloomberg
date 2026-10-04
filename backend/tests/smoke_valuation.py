"""Valuation API and append-only sourced observations; rollback fixtures."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.models.market import DailyPrice, MarketInstrument
from tests.test_valuation import SESSION, payload


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
                instrument = MarketInstrument(
                    symbol="VALUE" + uuid4().hex[:8],
                    exchange="NYSE",
                    name="Valuation fixture",
                    currency="USD",
                    price_provider="manual",
                    quote_multiplier=Decimal("1"),
                    registry_url="https://example.org/identity",
                    registry_observed_at=now,
                )
                session.add(instrument)
                await session.flush()
                session.add(
                    DailyPrice(
                        instrument_id=instrument.id,
                        session_date=SESSION,
                        close=Decimal("100"),
                        volume=0,
                        source_url="https://example.org/close",
                        fetched_at=now,
                        provider="manual",
                    )
                )
                await session.flush()
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    path = f"/api/v1/market/instruments/{instrument.id}/valuation"
                    assert (await client.get(path)).json()["calculation"]["status"] == "blocked"
                    response = await client.post(path, json=payload())
                    assert response.status_code == 201, response.text
                    assert response.json()["inserted"]
                    detail = (await client.get(path)).json()
                    assert detail["calculation"]["pe"] == "20.00"
                    assert detail["observation"]["source_url"] == payload()["source_url"]
                    assert not (await client.post(path, json=payload())).json()["inserted"]
                    repeated = (await client.get(path)).json()
                    assert len(repeated["history"]) == 1
                    assert (
                        repeated["observation"]["observed_at"]
                        == detail["observation"]["observed_at"]
                    )
                    assert (
                        await client.post(path, json=payload(currency="EUR"))
                    ).status_code == 400
                    assert (
                        await client.post(path, json=payload(security_basis_confirmed=False))
                    ).status_code == 422
                    assert (
                        await client.post(path, json=payload(eps_per_security="-5"))
                    ).status_code == 201
                    negative = (await client.get(path)).json()
                    assert negative["calculation"]["status"] == "blocked"
                    assert len(negative["history"]) == 2
                    # No fallback to the older positive observation.
                    assert negative["observation"]["eps_per_security"] == "-5"
                    session.add(
                        DailyPrice(
                            instrument_id=instrument.id,
                            session_date=SESSION + timedelta(days=1),
                            close=Decimal("110"),
                            volume=0,
                            source_url="https://example.org/newclose",
                            fetched_at=now,
                            provider="manual",
                        )
                    )
                    await session.flush()
                    changed = (await client.get(path)).json()
                    assert any("séance" in reason for reason in changed["calculation"]["reasons"])
                    assert (
                        await client.get(f"/api/v1/market/instruments/{uuid4()}/valuation")
                    ).status_code == 404
                print("Valuation PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
