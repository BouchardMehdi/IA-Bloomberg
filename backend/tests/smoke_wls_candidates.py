"""Partial WLS import, API mapping and replay against PostgreSQL; all fixtures rollback."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.wls import eligibility
from app.models.entity_registry import EntityRegistry
from app.models.market import MarketInstrument
from app.schemas.wls_candidates import CandidateManifest
from app.services.wls_candidates import REGISTRY, WlsCandidateService
from tests.test_wls_candidates import manifest


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
                await session.execute(delete(EntityRegistry).where(EntityRegistry.name == REGISTRY))
                await session.commit()
                service = WlsCandidateService(session)
                assert not (await service.detail())["loaded"]
                data = CandidateManifest.model_validate(manifest())
                assert (await service.load(data))["inserted"]
                instrument = MarketInstrument(
                    symbol="WLS" + uuid4().hex[:8],
                    exchange="XKRX",
                    name="WLS fixture",
                    currency="KRW",
                    price_provider="manual",
                    quote_multiplier=Decimal("1"),
                    registry_url="https://example.org/identity",
                    registry_observed_at=datetime.now(UTC),
                )
                session.add(instrument)
                await session.commit()
                instrument_id = str(instrument.id)
                payload = {
                    "instrument_id": instrument_id,
                    "bloomberg_identifier": "005930 KS Equity",
                    "correspondence_confirmed": True,
                    "note": "Preuve explicite du titre, classe et marché exacts.",
                    "source_url": "https://example.org/identity",
                    "as_of": datetime.now(UTC).date().isoformat(),
                }
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    base = "/api/v1/market/wls-candidates"
                    response = await client.get(base)
                    assert response.status_code == 200
                    assert response.json()["security_count"] == 1
                    assert response.json()["composition_as_of"] is None
                    assert (await client.get(base + "?search=absent")).json()["total"] == 0
                    assert (await client.get(base + "?search=005930&offset=1")).json()[
                        "items"
                    ] == []
                    assert (await client.get(base + "?limit=101")).status_code == 422
                    response = await client.post(base + "/mappings", json=payload)
                    assert response.status_code == 200, response.text
                    assert response.json()["inserted"]
                    first = (await client.get(base)).json()
                    assert first["mapped_count"] == 1
                    observed = first["items"][0]["listing_mapping"]["observed_at"]
                    assert not (await client.post(base + "/mappings", json=payload)).json()[
                        "inserted"
                    ]
                    assert not (await service.load(data))["inserted"]
                    replay = (await client.get(base)).json()
                    assert replay["items"][0]["listing_mapping"]["observed_at"] == observed
                    assert (
                        await client.post(
                            base + "/mappings",
                            json=payload
                            | {"note": "Une autre preuve ne doit pas remplacer la première."},
                        )
                    ).status_code == 400
                    # Candidate JSON never satisfies the eligibility guard, even after mapping.
                    registry = await session.get(EntityRegistry, REGISTRY)
                    await session.refresh(instrument)
                    assert eligibility(instrument, registry)["status"] != "verified"
                    assert (
                        await client.post(
                            base + "/mappings", json=payload | {"correspondence_confirmed": False}
                        )
                    ).status_code == 422
                print("WLS candidates PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                await session.close()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
