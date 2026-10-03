"""PostgreSQL ranking checks with all fixture writes rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.research_ranking as ranking_module
from app.db.session import engine, get_db_session
from app.main import app
from app.models.article import Article
from app.models.company import Company, EventCompany
from app.models.entity_registry import EntityRegistry
from app.models.event import Event, EventArticle
from app.models.market import DailyPrice, MarketInstrument
from app.models.source import Source
from app.services.research_ranking import ResearchRankingService


async def main():
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                now = datetime.now(UTC)
                suffix = uuid4().hex[:8]
                cik = str(int(suffix, 16)).zfill(10)
                tracked = []
                for symbol, issuer, currency, venue in [
                    ("A" + suffix.upper(), cik, "USD", "NYSE"),
                    ("B" + suffix.upper(), cik, "USD", "NYSE"),
                    ("02600" + suffix.upper(), None, "TWD", "XTAI"),
                ]:
                    instrument = MarketInstrument(
                        symbol=symbol,
                        cik=issuer,
                        currency=currency,
                        exchange=venue,
                        name="Ranking fixture only",
                        price_provider="manual",
                        registry_url="https://example.org/fixture",
                        registry_observed_at=now,
                        quote_multiplier=Decimal("1"),
                    )
                    session.add(instrument)
                    tracked.append(instrument)
                source = Source(
                    name="Ranking " + suffix,
                    source_type="rss",
                    url="https://example.org/ranking-" + suffix,
                )
                company = Company(cik=cik, name="Fixture issuer " + suffix)
                session.add_all([source, company])
                await session.flush()

                async def publication(when):
                    token = uuid4().hex
                    article = Article(
                        source_id=source.id,
                        title="Fixture publication",
                        url="https://example.org/" + token,
                        published_at=when,
                        fetched_at=now,
                        content_hash=token * 2,
                    )
                    parent = Event(
                        deduplication_key=token,
                        title="Fixture filing",
                        event_type="regulatory_filing",
                        event_datetime=now + timedelta(days=40),
                        structured_data={},
                    )
                    session.add_all([article, parent])
                    await session.flush()
                    session.add_all(
                        [
                            EventArticle(
                                event_id=parent.id, article_id=article.id, is_primary_source=True
                            ),
                            EventCompany(event_id=parent.id, company_id=company.id),
                        ]
                    )
                    await session.flush()
                    return parent, article

                parent, article = await publication(now - timedelta(days=1))

                async def fact(parent, article, status="resolved", documentary=False, merged=False):
                    row = Event(
                        deduplication_key=uuid4().hex,
                        parent_event_id=parent.id,
                        title="Fixture result",
                        event_type="financial_results",
                        evidence_excerpt="Fixture reports results",
                        structured_data={
                            "fact": {"summary": "Fixture reports its results"},
                            "entity_resolution": {
                                "entities": []
                                if documentary
                                else [
                                    {
                                        "status": status,
                                        "kind": "equity",
                                        "role": "subject",
                                        "quote": tracked[0].symbol,
                                        "candidates": [
                                            {
                                                "cik": cik,
                                                "ticker": tracked[0].symbol,
                                                "exchange": "NYSE",
                                            }
                                        ],
                                    }
                                ]
                            },
                        },
                        merged_into_event_id=parent.id if merged else None,
                    )
                    session.add(row)
                    await session.flush()
                    session.add(
                        EventArticle(event_id=row.id, article_id=article.id, is_primary_source=True)
                    )
                    if documentary:
                        session.add(EventCompany(event_id=row.id, company_id=company.id))
                    await session.flush()
                    return row

                first_fact = await fact(parent, article)
                await fact(parent, article)
                grouped_parent, grouped_article = await publication(now - timedelta(days=1))
                grouped_parent.merged_into_event_id = parent.id
                await fact(grouped_parent, grouped_article)
                await fact(parent, article, status="ambiguous")
                await fact(parent, article, documentary=True)
                merged = await fact(parent, article, merged=True)
                for when in (now - timedelta(days=40), now + timedelta(days=1), None):
                    excluded_parent, excluded_article = await publication(when)
                    await fact(excluded_parent, excluded_article)
                    if when is not None and when < now:
                        republished_parent, republished_article = await publication(now)
                        republished_parent.merged_into_event_id = excluded_parent.id
                        await fact(republished_parent, republished_article)
                await session.commit()
                service = ResearchRankingService(session)
                result = await service.ranking(limit=50)
                by_id = {r["instrument"]["id"]: r for r in result["items"]}
                a, b, international = [by_id[i.id] for i in tracked]
                assert a["score"] == 90 and b["score"] == 75 and international["score"] == 0
                assert a["recent_fact_count"] == 3 and a["recent_publication_count"] == 1
                assert a["scored_publication_count"] == 1 and len(a["facts"]) == 1
                assert all(f["event_id"] != merged.id for f in a["facts"])
                assert a["rank"] < b["rank"] and a["data_checks"][0]["status"] == "missing"
                assert a["wls_eligibility"]["status"] != "verified"
                assert b["facts"][0]["relationship"]["basis"] == "issuer_mention"
                assert any("CIK non fourni" in check for check in international["checks"])
                session.add(
                    DailyPrice(
                        instrument_id=tracked[0].id,
                        session_date=now.date(),
                        close=Decimal("100"),
                        volume=1000,
                        fetched_at=now,
                        source_url="https://example.org/fixture-price",
                    )
                )
                universe = {
                    "source_url": "https://example.org/fixture-wls",
                    "observed_at": now,
                    "content_hash": "0" * 64,
                    "records": [
                        {
                            "security_id": "fixture-" + suffix,
                            "symbol": tracked[0].symbol,
                            "exchange": "NYSE",
                            "asset_class": "equity",
                            "as_of": now.date().isoformat(),
                        }
                    ],
                }
                await session.execute(
                    insert(EntityRegistry)
                    .values(name="wls_universe", **universe)
                    .on_conflict_do_update(index_elements=[EntityRegistry.name], set_=universe)
                )
                await session.commit()
                updated = await service.ranking(limit=50)
                by_id = {r["instrument"]["id"]: r for r in updated["items"]}
                assert by_id[tracked[0].id]["score"] == 90, (
                    "Price and eligibility never alter research score"
                )
                assert by_id[tracked[0].id]["wls_eligibility"]["status"] == "verified"
                assert by_id[tracked[1].id]["wls_eligibility"]["status"] == "not_verified", (
                    "A shared CIK does not transfer WLS membership"
                )
                assert by_id[tracked[0].id]["data_checks"][1]["status"] == "not_required"

                async def fixture_session():
                    yield session

                app.dependency_overrides[get_db_session] = fixture_session
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as http:
                        first = (await http.get("/api/v1/market/research-ranking?limit=1")).json()
                        second = (
                            await http.get(
                                f"/api/v1/market/research-ranking?limit=1&offset={first['next_offset']}"
                            )
                        ).json()
                        assert len(first["items"]) == len(second["items"]) == 1
                        assert (
                            first["items"][0]["instrument"]["id"]
                            != second["items"][0]["instrument"]["id"]
                        )
                        assert (
                            first["total_tracked"] >= 3
                            and first["method_version"] == "research-priority-v1"
                        )
                        assert first["items"][0]["facts"][0]["sources"][0]["published_at"]
                        assert isinstance(first["items"][0]["usd_valuation"]["price_usd"], str)
                finally:
                    app.dependency_overrides.pop(get_db_session, None)
                original_limit = ranking_module.MAX_EVENTS
                try:
                    ranking_module.MAX_EVENTS = 1
                    bounded = await service.ranking()
                    assert (
                        bounded["coverage"]["limited"]
                        and bounded["coverage"]["events_examined"] == 1
                    )
                finally:
                    ranking_module.MAX_EVENTS = original_limit
                assert first_fact.id is not None
                print(
                    "Research ranking smoke passed: sourced scoring, share classes, "
                    "deduplication, dates, WLS, pagination and bounded coverage"
                )
        finally:
            await outer.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
