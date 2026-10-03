"""PostgreSQL integration check; simulated prices and trades are always rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.alpha_vantage import AlphaVantageClient
from app.models.article import Article
from app.models.entity_registry import EntityRegistry
from app.models.event import Event, EventArticle
from app.models.market import MarketInstrument
from app.models.portfolio import PaperTrade
from app.models.source import Source
from app.schemas.market import PaperOrder, PortfolioCreate
from app.services.market_data import MarketDataService
from app.services.paper_portfolio import PaperPortfolioService


async def main():
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                instrument = MarketInstrument(
                    symbol="TEST" + uuid4().hex[:8].upper(),
                    name="Fixture only",
                    exchange="NYSE",
                    cik="0000000001",
                    currency="USD",
                    registry_url="https://www.sec.gov/fixture",
                    registry_observed_at=datetime.now(UTC),
                )
                session.add(instrument)
                await session.commit()
                today = datetime.now(UTC).date()
                calls = []

                def handler(request):
                    symbol = request.url.params["symbol"]
                    calls.append(symbol)
                    return httpx.Response(
                        200,
                        json={
                            "Meta Data": {"2. Symbol": symbol},
                            "Time Series (Daily)": {
                                today.isoformat(): {"4. close": "100.00", "5. volume": "1000"},
                            },
                        },
                    )

                market = MarketDataService(session)
                client = AlphaVantageClient("fixture-key", transport=httpx.MockTransport(handler))
                await market.collect(client, limit=25)
                assert instrument.symbol in calls
                before = len(calls)
                await market.collect(client, limit=25)
                assert len(calls) == before, "Daily cache must avoid repeat provider calls"
                service = PaperPortfolioService(session)
                created = await service.create(
                    PortfolioCreate(
                        name="Fixture",
                        initial_capital="10000",
                        max_position_pct="25",
                        allowed_symbols=[instrument.symbol],
                    )
                )
                portfolio_id = created["id"]
                order = PaperOrder(
                    instrument_id=instrument.id, client_order_id=uuid4(), side="buy", quantity=10
                )
                try:
                    await service.order(portfolio_id, order)
                except ValueError as error:
                    assert "WLS" in str(error)
                else:
                    raise AssertionError("An unverified WLS action must not be bought")
                fixture_universe = {
                    "source_url": "https://example.com/wls-fixture",
                    "observed_at": datetime.now(UTC),
                    "content_hash": "0" * 64,
                    "records": [
                        {
                            "security_id": "fixture-security",
                            "symbol": instrument.symbol,
                            "exchange": "NYSE",
                            "asset_class": "equity",
                            "as_of": today.isoformat(),
                        }
                    ],
                }
                await session.execute(
                    insert(EntityRegistry)
                    .values(name="wls_universe", **fixture_universe)
                    .on_conflict_do_update(
                        index_elements=[EntityRegistry.name], set_=fixture_universe
                    )
                )
                await session.commit()
                first = await service.order(portfolio_id, order)
                replay = await service.order(portfolio_id, order)
                assert first["id"] == replay["id"]
                count = (
                    await session.execute(
                        select(func.count())
                        .select_from(PaperTrade)
                        .where(PaperTrade.portfolio_id == portfolio_id)
                    )
                ).scalar_one()
                assert count == 1
                snapshot = await service.snapshot(portfolio_id)
                assert snapshot["cash"] == Decimal("8999")
                assert snapshot["total_pnl"] == Decimal("-1")
                assert snapshot["positions"][0]["quantity"] == 10
                for side, quantity in (("buy", 90), ("buy", 20), ("sell", 11)):
                    try:
                        await service.order(
                            portfolio_id,
                            PaperOrder(
                                instrument_id=instrument.id,
                                client_order_id=uuid4(),
                                side=side,
                                quantity=quantity,
                            ),
                        )
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Unsafe order must be blocked")
                quote = await market.latest_price(instrument.id)
                quote.session_date = today - timedelta(days=20)
                await session.commit()
                try:
                    await service.order(
                        portfolio_id,
                        PaperOrder(
                            instrument_id=instrument.id,
                            client_order_id=uuid4(),
                            side="sell",
                            quantity=1,
                        ),
                    )
                except ValueError:
                    pass
                else:
                    raise AssertionError("Stale quote must block a fill")
                quote.session_date = today
                quote.close = Decimal("120")
                await session.commit()
                sold = await service.order(
                    portfolio_id,
                    PaperOrder(
                        instrument_id=instrument.id,
                        client_order_id=uuid4(),
                        side="sell",
                        quantity=10,
                    ),
                )
                assert sold["realized_pnl"] == Decimal("197.80")
                snapshot = await service.snapshot(portfolio_id)
                assert snapshot["positions"] == [] and snapshot["total_pnl"] == Decimal("197.80")
                assert "fixture-key" not in sold["quote_source_url"]

                async def fixture_session():
                    yield session

                app.dependency_overrides[get_db_session] = fixture_session
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as http:
                        response = await http.get(f"/api/v1/market/portfolios/{portfolio_id}")
                        assert response.status_code == 200
                        assert response.json()["total_pnl"] == "197.80"
                        assert response.json()["positions"] == []
                        fixture_id = uuid4().hex
                        source = Source(
                            name="Research fixture " + fixture_id,
                            source_type="rss",
                            url="https://example.org/fixture",
                        )
                        session.add(source)
                        await session.flush()
                        article = Article(
                            source_id=source.id,
                            title="Research fixture",
                            url="https://example.org/" + fixture_id,
                            content_hash=fixture_id * 2,
                            published_at=datetime.now(UTC),
                            fetched_at=datetime.now(UTC),
                        )
                        session.add(article)
                        await session.flush()
                        fact = Event(
                            deduplication_key="research-fixture-" + uuid4().hex,
                            event_type="company_event",
                            title="Fixture research",
                            status="detected",
                            evidence_excerpt=instrument.symbol,
                            structured_data={
                                "entity_resolution": {
                                    "entities": [
                                        {
                                            "status": "resolved",
                                            "kind": "equity",
                                            "role": "counterparty",
                                            "quote": instrument.symbol,
                                            "candidates": [
                                                {
                                                    "cik": instrument.cik,
                                                    "ticker": instrument.symbol,
                                                    "exchange": instrument.exchange,
                                                }
                                            ],
                                        }
                                    ]
                                }
                            },
                        )
                        session.add(fact)
                        await session.flush()
                        session.add(
                            EventArticle(
                                event_id=fact.id, article_id=article.id, is_primary_source=True
                            )
                        )
                        await session.commit()
                        response = await http.get(
                            f"/api/v1/market/instruments/{instrument.id}/research"
                        )
                        assert response.status_code == 200
                        data = response.json()
                        card = next(c for c in data["items"] if c["event_id"] == str(fact.id))
                        assert card["relationship"]["basis"] == "security_mention"
                        assert card["relationship"]["role"] == "counterparty"
                        assert isinstance(data["instrument"]["latest_price"]["close"], str)
                        assert Decimal(data["instrument"]["latest_price"]["close"]) == Decimal(
                            "120"
                        )
                        assert (
                            await http.get(f"/api/v1/market/instruments/{uuid4()}/research")
                        ).status_code == 404
                finally:
                    app.dependency_overrides.pop(get_db_session, None)
                print(
                    "PostgreSQL market smoke passed: cache, fees, idempotent ledger, "
                    "limits, stale prices and P&L"
                )
        finally:
            await outer.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
