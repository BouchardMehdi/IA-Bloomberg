"""PostgreSQL FX ingestion check: mocked HTTP, every write rolled back."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import engine, get_db_session
from app.main import app
from app.market.ecb_fx import EcbFxClient
from app.models.market import FxCollectionRun, FxRate
from app.schemas.international import FxRateCreate
from app.services.fx_collection import FxCollectionService
from app.services.international_market import InternationalMarketService
from app.services.usd_valuation import UsdValuationService

FIXTURE = (Path(__file__).parent / "fixtures" / "ecb_fx_90d.xml").read_bytes()


async def main():
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                await session.execute(select(func.pg_advisory_xact_lock(721904)))
                await session.execute(delete(FxCollectionRun))
                await session.execute(
                    delete(FxRate).where(
                        FxRate.rate_date.in_([date(2020, 1, 2), date(2020, 1, 3)]),
                        FxRate.currency.in_(["EUR", "GBP", "HKD"]),
                    )
                )
                session.add(
                    FxRate(
                        currency="HKD",
                        rate_date=date(2020, 1, 3),
                        usd_per_unit=Decimal("0.2"),
                        source_url="https://example.org/manual",
                        fetched_at=datetime.now(UTC),
                    )
                )
                await session.commit()
                calls = []

                def handler(request):
                    calls.append(str(request.url))
                    return httpx.Response(200, content=FIXTURE)

                service = FxCollectionService(session)
                client = EcbFxClient(transport=httpx.MockTransport(handler))
                first = await service.collect(client)
                assert first["status"] == "success" and first["record_count"] == 6
                assert first["preserved_manual_count"] == 1
                assert first["available_currencies"] == ["EUR", "GBP", "HKD"]
                assert (await service.collect(client))["status"] == "skipped" and len(calls) == 1
                manual = (
                    await session.execute(
                        select(FxRate).where(
                            FxRate.currency == "HKD", FxRate.rate_date == date(2020, 1, 3)
                        )
                    )
                ).scalar_one()
                assert manual.provider == "manual" and manual.usd_per_unit == Decimal("0.2")

                quote = await UsdValuationService(session).quote(
                    SimpleNamespace(currency="GBP", quote_multiplier=Decimal("1")),
                    SimpleNamespace(
                        close=Decimal("100"),
                        session_date=date(2020, 1, 3),
                        source_url="https://example.org/price",
                        fetched_at=datetime.now(UTC),
                    ),
                )
                assert quote["price_usd"] == Decimal("150")
                assert quote["conversion"]["fx_provider"] == "ecb"
                assert quote["conversion"]["fx_derivation"]["usd_per_eur"] == "1.20"
                run = await session.get(FxCollectionRun, first["id"])
                run.started_at -= timedelta(
                    minutes=get_settings().fx_collection_interval_minutes + 1
                )
                await session.commit()
                count_before = (
                    await session.execute(select(func.count()).select_from(FxRate))
                ).scalar_one()
                failed = await service.collect(
                    EcbFxClient(
                        transport=httpx.MockTransport(
                            lambda request: httpx.Response(200, content=b"invalid xml")
                        )
                    )
                )
                assert (
                    failed["status"] == "failed"
                    and failed["error_code"] == "invalid_reference_payload"
                )
                assert (
                    await session.execute(select(func.count()).select_from(FxRate))
                ).scalar_one() == count_before
                status = await service.status()
                assert status["latest_run"]["status"] == "failed"
                assert status["last_success"]["id"] == first["id"]

                await InternationalMarketService(session).save_fx(
                    FxRateCreate(
                        currency="EUR",
                        usd_per_unit="9",
                        as_of=date(2020, 1, 3),
                        source_url="https://example.org/override",
                    )
                )
                latest = await session.get(FxCollectionRun, failed["id"])
                latest.started_at -= timedelta(
                    minutes=get_settings().fx_collection_interval_minutes + 1
                )
                await session.commit()
                assert (await service.collect(client))["preserved_manual_count"] == 2
                session.expire_all()
                override = (
                    await session.execute(
                        select(FxRate).where(
                            FxRate.currency == "EUR", FxRate.rate_date == date(2020, 1, 3)
                        )
                    )
                ).scalar_one()
                assert override.provider == "manual" and override.derivation is None
                assert override.usd_per_unit == Decimal("9")

                async def fixture_session():
                    yield session

                app.dependency_overrides[get_db_session] = fixture_session
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as http:
                        response = await http.get("/api/v1/market/fx-collection")
                        assert response.status_code == 200
                        assert response.json()["last_success"]["record_count"] == 6
                finally:
                    app.dependency_overrides.pop(get_db_session, None)
                print(
                    "FX smoke passed: atomic history, cache, manual priority, "
                    "failed feed preservation, derivation evidence and API"
                )
        finally:
            await outer.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
