"""No external network: reservations, FIGI proofs, ledger policy and export history."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.openfigi import OpenFigiClient
from app.models.entity_registry import EntityRegistry
from app.models.market import DailyPrice, MarketInstrument
from app.models.wls_identity import WlsIdentityObservation
from app.schemas.wls_candidates import CandidateManifest
from app.services.wls_automation import STATE, WlsAutomationService
from app.services.wls_candidates import REGISTRY, WlsCandidateService
from tests.test_openfigi import record
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
                await session.execute(
                    delete(EntityRegistry).where(
                        EntityRegistry.name.in_(
                            [
                                REGISTRY,
                                STATE,
                                "wls_universe",
                                "wls_archive_" + "a" * 32,
                                "wls_archive_" + "b" * 32,
                            ]
                        )
                    )
                )
                await session.execute(
                    delete(WlsIdentityObservation).where(
                        WlsIdentityObservation.source_hash == "a" * 64
                    )
                )
                await session.commit()
                symbol = "QA" + uuid4().hex[:8].upper()
                data = manifest()
                data["records"][0].update(
                    bloomberg_identifier=f"{symbol} US Equity",
                    bloomberg_ticker=symbol,
                    bloomberg_market_code="US",
                )
                service = WlsCandidateService(session)
                await service.load(CandidateManifest.model_validate(data))
                now = datetime.now(UTC)
                instrument = MarketInstrument(
                    symbol=symbol,
                    exchange="NYSE",
                    name="WLS test",
                    currency="USD",
                    price_provider="manual",
                    quote_multiplier=Decimal("1"),
                    registry_url="https://example.org/identity",
                    registry_observed_at=now,
                )
                session.add(instrument)
                await session.flush()
                instrument_id = instrument.id
                session.add(
                    DailyPrice(
                        instrument_id=instrument_id,
                        session_date=now.date(),
                        close=Decimal("100"),
                        volume=100,
                        source_url="https://example.org/close",
                        fetched_at=now,
                        provider="manual",
                    )
                )
                await session.commit()

                def respond(request):
                    import json

                    jobs = json.loads(request.content)
                    return httpx.Response(
                        200,
                        json=[
                            {
                                "data": [
                                    record(
                                        ticker=symbol,
                                        figi="BBG000B9XRY4"
                                        if job["idType"] == "TICKER"
                                        else "BBG000B9Y5X2",
                                        exchCode="US" if job["idType"] == "TICKER" else "UN",
                                    )
                                ]
                            }
                            for job in jobs
                        ],
                    )

                automation = WlsAutomationService(session)
                client = OpenFigiClient(httpx.MockTransport(respond))
                assert (await automation.collect(client))["attempted"] == 1
                assert (await automation.collect(client))["status"] == "waiting"
                state = await session.get(EntityRegistry, STATE)
                state.records = [{"next_attempt_at": (now - timedelta(seconds=1)).isoformat()}]
                await session.commit()
                assert (await automation.collect(client))["attempted"] == 1
                instrument = await session.get(MarketInstrument, instrument_id)
                assert (await automation.assessments([instrument]))[str(instrument_id)][
                    "status"
                ] == "matched"
                observations = (
                    (
                        await session.execute(
                            select(WlsIdentityObservation).where(
                                WlsIdentityObservation.source_hash == "a" * 64
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(observations) == 2

                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as api:
                    base = "/api/v1/market"
                    response = await api.post(
                        base + "/portfolios",
                        json={"name": "Provisional", "wls_policy": "declared_partial"},
                    )
                    assert response.status_code == 201, response.text
                    provisional = response.json()["id"]
                    response = await api.post(base + "/portfolios", json={"name": "Strict"})
                    strict = response.json()["id"]
                    order = {
                        "instrument_id": str(instrument_id),
                        "side": "buy",
                        "quantity": 1,
                        "client_order_id": str(uuid4()),
                    }
                    path = base + f"/portfolios/{provisional}/orders"
                    response = await api.post(path, json=order)
                    assert response.status_code == 200, response.text
                    trade = response.json()
                    assert trade["universe_evidence"]["policy"] == "declared_partial"
                    assert trade["universe_evidence"]["composition_as_of"] is None
                    assert len(trade["universe_evidence"]["observations"]) == 2
                    assert (await api.post(path, json=order)).json()["id"] == trade["id"]
                    assert (
                        await api.post(base + f"/portfolios/{strict}/orders", json=order)
                    ).status_code == 400
                    # Export changes retain trade evidence and require new membership checks.
                    replacement = manifest() | {"source_sha256": "b" * 64}
                    await service.load(CandidateManifest.model_validate(replacement))
                    detail = (await api.get(base + "/wls-candidates")).json()
                    assert len(detail["archive_history"]) == 1
                    assert detail["automatic_mapped_count"] == 0
                    saved = (await api.get(base + f"/portfolios/{provisional}")).json()
                    assert saved["trades"][0]["universe_evidence"]["source_hash"] == "a" * 64
                    rejected = await api.post(path, json=order | {"client_order_id": str(uuid4())})
                    assert rejected.status_code == 400
                    # Replay is still idempotent after membership changes.
                    assert (await api.post(path, json=order)).json()["id"] == trade["id"]
                    sale = await api.post(
                        path, json=order | {"side": "sell", "client_order_id": str(uuid4())}
                    )
                    assert sale.status_code == 200, sale.text
                    await service.load(CandidateManifest.model_validate(data))
                    assert not (await service.load(CandidateManifest.model_validate(data)))[
                        "inserted"
                    ]
                    # Batch rejects unknown candidates without discarding a valid line.
                    mapping = {
                        "instrument_id": str(instrument_id),
                        "bloomberg_identifier": f"{symbol} US Equity",
                        "correspondence_confirmed": True,
                        "note": "Cotation exacte déclarée selon la preuve.",
                        "source_url": "https://example.org/identity",
                        "as_of": now.date().isoformat(),
                    }
                    batch = await api.post(
                        base + "/wls-candidates/mappings/batch",
                        json={
                            "items": [
                                mapping,
                                mapping | {"bloomberg_identifier": "ABSENT US Equity"},
                            ]
                        },
                    )
                    assert batch.json()["saved"] == 1, batch.text
                    assert batch.json()["items"][1]["status"] == "rejected"
                print("WLS automation PostgreSQL/API smoke passed; fixtures rolled back.")
            finally:
                app.dependency_overrides.pop(get_db_session, None)
                await session.close()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
