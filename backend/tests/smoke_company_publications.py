"""Targeted collection, issuer links and API in PostgreSQL; fixtures rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.company_sec import SECCompanyCollector
from app.db.session import engine, get_db_session
from app.main import app
from app.models.article import Article
from app.models.company import Company, EventCompany
from app.models.market import MarketInstrument
from app.models.source import Source
from app.repositories.events import EventRepository, PendingArticle
from app.services.company_publications import CompanyPublicationService
from app.services.instrument_research import InstrumentResearchService


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
                for venue in ["NYSE", "Nasdaq"]:
                    instrument = MarketInstrument(
                        symbol="PUB" + uuid4().hex[:8],
                        exchange=venue,
                        cik=cik,
                        name="Fixture",
                        currency="USD",
                        price_provider="manual",
                        registry_url="https://example.org/registry",
                        registry_observed_at=now,
                    )
                    session.add(instrument)
                    instruments.append(instrument)
                await session.commit()
                calls = []
                payload = {
                    "cik": cik,
                    "name": "Fixture Corporation",
                    "filings": {
                        "recent": {
                            "form": ["10-Q", "8-K"],
                            "accessionNumber": [f"{cik}-26-000001", f"{cik}-26-000002"],
                            "acceptanceDateTime": [
                                (now - timedelta(days=1)).isoformat(),
                                (now - timedelta(days=2)).isoformat(),
                            ],
                            "primaryDocument": ["quarter.htm", "announcement.htm"],
                        }
                    },
                }

                def respond(request):
                    calls.append(request)
                    return httpx.Response(200, json=payload)

                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:

                    def factory(cik_value, user_agent):
                        return SECCompanyCollector(cik_value, user_agent, client=client)

                    with patch("app.services.company_publications.SECCompanyCollector", factory):
                        async with httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=app), base_url="http://test"
                        ) as api:
                            path = f"/api/v1/market/instruments/{instruments[0].id}/publications"
                            assert (await api.get(path + "/collection")).json()[
                                "status"
                            ] == "pending"
                            response = await api.post(path + "/collect")
                            assert response.status_code == 200 and response.json()["inserted"] == 2
                            result = await api.post(
                                f"/api/v1/market/instruments/{instruments[1].id}/publications/collect"
                            )
                            assert result.json()["status"] == "cached_or_retry_pending"
                            assert len(calls) == 1
                            status = (await api.get(path + "/collection")).json()
                            assert status["fetched_count"] == 2 and status["supported"]
                # Same extraction path as the scheduler; scoped to fixture sources.
                rows = (
                    await session.execute(
                        select(Article, Source)
                        .join(Source)
                        .where(Source.name == f"SEC company {cik}")
                    )
                ).all()
                for article, source in rows:
                    await EventRepository(session).add_from_article(PendingArticle(article, source))
                await session.commit()
                detail = await InstrumentResearchService(session).detail(instruments[1].id, 20, 0)
                assert len(detail["items"]) == 2
                assert all(
                    card["relationship"]["basis"] == "issuer_document" for card in detail["items"]
                )
                assert all(card["kind"] == "publication" for card in detail["items"])
                assert all(card["summary"] is None for card in detail["items"])
                assert (
                    await session.execute(
                        select(func.count())
                        .select_from(EventCompany)
                        .join(Company)
                        .where(Company.cik == cik)
                    )
                ).scalar_one() == 2
                assert (await CompanyPublicationService(session).collect_scheduled(limit=0))[
                    "attempts"
                ] == 0
                # Failed response keeps every previously inserted document.
                rows_run = await CompanyPublicationService(session).latest(cik)
                rows_run.started_at = now - timedelta(hours=2)
                await session.commit()
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(403, text="Do not retain response")
                    )
                ) as client:
                    failed = SECCompanyCollector(cik, "Fixture test@example.org", client=client)
                    result = await CompanyPublicationService(session).collect(
                        instruments[0].id, collector=failed
                    )
                    assert result["error"] == "sec_http_error"
                    status = await CompanyPublicationService(session).status(instruments[0].id)
                    assert status["status"] == "failed" and "Do not retain" not in status["error"]
                    assert (
                        await CompanyPublicationService(session).collect(
                            instruments[0].id, collector=failed
                        )
                    )["status"] == "cached_or_retry_pending"
                assert (
                    await session.execute(
                        select(func.count())
                        .select_from(Article)
                        .join(Source)
                        .where(Source.name == f"SEC company {cik}")
                    )
                ).scalar_one() == 2
                print(
                    "Company-publication PostgreSQL/API smoke passed; "
                    "issuer context verified; fixtures rolled back."
                )
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
