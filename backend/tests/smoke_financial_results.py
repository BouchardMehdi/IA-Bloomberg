"""Financial collection/API in PostgreSQL; all fixture data rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.sec_financials import FinancialRecord
from app.models.financial_fact import FinancialFact
from app.models.market import MarketInstrument
from app.services.financial_results import FinancialResultsService


class FixtureClient:
    def __init__(self, cik):
        self.cik = cik
        self.source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        self.calls = 0
        self.invalid = False

    async def fetch(self):
        self.calls += 1
        today = datetime.now(UTC).date()
        rows = []
        for concept, metric, unit, value, days in [
            ("Revenues", "revenue", "USD", "1000000", 90),
            ("Revenues", "revenue", "USD", "3000000", 270),
            ("NetIncomeLoss", "net_income", "USD", "-100", 90),
            ("EarningsPerShareDiluted", "eps_diluted", "USD/shares", "0", 90),
        ]:
            rows.append(
                FinancialRecord(
                    metric=metric,
                    concept=concept,
                    unit=unit,
                    value=value,
                    start=today - timedelta(days=days + 10),
                    end=today - timedelta(days=10),
                    filed=today - timedelta(days=1),
                    accession=f"{self.cik}-26-000001",
                    form="10-Q",
                    fiscal_year=2026,
                    filing_period="Q3",
                )
            )
        if self.invalid:
            rows[-1] = rows[-1].model_copy(update={"value": Decimal("NaN")})
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
                instruments = []
                for exchange, identity in [("NYSE", cik), ("Nasdaq", cik), ("XHKG", None)]:
                    instrument = MarketInstrument(
                        symbol="FIN" + uuid4().hex[:8],
                        exchange=exchange,
                        cik=identity,
                        name="Financial fixture",
                        currency="USD",
                        price_provider="manual",
                        registry_url="https://example.org/fixture",
                        registry_observed_at=now,
                    )
                    session.add(instrument)
                    instruments.append(instrument)
                await session.commit()
                fixture = FixtureClient(cik)
                service = FinancialResultsService(session)
                with patch(
                    "app.services.financial_results.SecFinancialClient",
                    lambda cik, user_agent: fixture,
                ):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as api:
                        path = f"/api/v1/market/instruments/{instruments[0].id}/financials"
                        saved = await api.post(path + "/collect")
                        assert saved.status_code == 200 and saved.json()["inserted"] == 4
                        second = await api.post(
                            f"/api/v1/market/instruments/{instruments[1].id}/financials/collect"
                        )
                        assert (
                            second.json()["status"] == "cached_or_retry_pending"
                            and fixture.calls == 1
                        )
                        data = (await api.get(path + "?limit=2")).json()
                        assert len(data["items"]) == 2 and data["next_offset"] == 2
                        assert (await api.get(path + "?limit=0")).status_code == 422
                        assert (
                            await api.get(f"/api/v1/market/instruments/{uuid4()}/financials")
                        ).status_code == 404
                        missing = await api.get(
                            f"/api/v1/market/instruments/{instruments[2].id}/financials"
                        )
                        assert (
                            not missing.json()["collection"]["supported"]
                            and missing.json()["items"] == []
                        )
                detail = await service.detail(instruments[1].id, 50, 0)
                assert len(detail["items"]) == 4
                assert len({item["start"] for item in detail["items"]}) == 2
                eps = next(item for item in detail["items"] if item["metric"] == "eps_diluted")
                assert eps["value"] == "0" and eps["comparison"]["status"] == "not_comparable"
                observed = {item["id"]: item["observed_at"] for item in detail["items"]}
                run = await service.latest(cik)
                run.started_at = now - timedelta(days=2)
                await session.commit()
                assert (await service.collect(instruments[0].id, client=fixture))["inserted"] == 0
                detail = await service.detail(instruments[0].id, 50, 0)
                assert observed == {item["id"]: item["observed_at"] for item in detail["items"]}
                run = await service.latest(cik)
                run.started_at = now - timedelta(days=2)
                await session.commit()
                fixture.invalid = True
                failed = await service.collect(instruments[0].id, client=fixture)
                assert failed["status"] == "failed" and failed["error"] == "sec_invalid_response"
                assert (
                    await session.execute(
                        select(func.count())
                        .select_from(FinancialFact)
                        .where(FinancialFact.cik == cik)
                    )
                ).scalar_one() == 4
                assert (await service.collect(instruments[0].id, client=fixture))[
                    "status"
                ] == "cached_or_retry_pending"
                assert (await service.collect_scheduled(limit=0))["attempts"] == 0
                print(
                    "Financial-results PostgreSQL/API smoke passed; "
                    "history and issuer scope preserved."
                )
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
