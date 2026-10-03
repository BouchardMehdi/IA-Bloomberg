"""Real PostgreSQL/API check, all supplied fixtures rolled back; no network calls."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.alpha_vantage import AlphaVantageClient
from app.models.entity_registry import EntityRegistry
from app.models.market import FxRate, MarketInstrument
from app.services.market_data import MarketDataService


async def main():
    async with engine.connect() as connection:
        outer = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:

                async def fixture_session():
                    yield session

                app.dependency_overrides[get_db_session] = fixture_session
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app), base_url="http://test"
                    ) as http:
                        today = datetime.now(UTC).date()

                        def day(ago):
                            return (today - timedelta(days=ago)).isoformat()

                        # Isolate the fixture currency within the outer rollback transaction.
                        await session.execute(delete(FxRate).where(FxRate.currency == "HKD"))
                        await session.commit()
                        symbol = "26" + uuid4().hex[:8].upper()
                        identity = {
                            "symbol": symbol,
                            "exchange": "XTST",
                            "name": "Fixture only",
                            "isin": "US0378331005",
                            "currency": "HKD",
                            "quote_multiplier": "1",
                            "asset_class": "equity",
                            "as_of": day(1),
                            "source_url": "https://example.org/identity",
                        }
                        response = await http.post(
                            "/api/v1/market/international-instruments", json=identity
                        )
                        assert response.status_code == 201, response.text
                        instrument_id = response.json()["id"]
                        assert (
                            await http.post(
                                "/api/v1/market/international-instruments", json=identity
                            )
                        ).json()["id"] == instrument_id
                        conflict = {**identity, "currency": "JPY"}
                        assert (
                            await http.post(
                                "/api/v1/market/international-instruments", json=conflict
                            )
                        ).status_code == 400
                        other_listing = {**identity, "exchange": "XTS2"}
                        assert (
                            await http.post(
                                "/api/v1/market/international-instruments", json=other_listing
                            )
                        ).json()["id"] != instrument_id

                        price = {
                            "currency": "HKD",
                            "quote_multiplier": "1",
                            "close": "100",
                            "volume": 1000,
                            "as_of": day(1),
                            "source_url": "https://example.org/close",
                        }
                        price_path = f"/api/v1/market/instruments/{instrument_id}/prices"
                        assert (
                            await http.post(price_path, json={**price, "quote_multiplier": "0.01"})
                        ).status_code == 400
                        assert (await http.post(price_path, json=price)).status_code == 200
                        fx = {
                            "currency": "HKD",
                            "usd_per_unit": "0.5",
                            "as_of": day(0),
                            "source_url": "https://example.org/rate",
                        }
                        assert (
                            await http.post("/api/v1/market/fx-rates", json=fx)
                        ).status_code == 200
                        research_path = f"/api/v1/market/instruments/{instrument_id}/research"
                        # Later FX observations must never convert an older close.
                        valuation = (await http.get(research_path)).json()["instrument"][
                            "usd_valuation"
                        ]
                        assert valuation["status"] == "missing_fx"
                        portfolio_id = (
                            await http.post(
                                "/api/v1/market/portfolios",
                                json={
                                    "name": "International fixture",
                                    "initial_capital": "10000",
                                    "max_position_pct": "100",
                                    "fee_bps": "10",
                                },
                            )
                        ).json()["id"]
                        order_path = f"/api/v1/market/portfolios/{portfolio_id}/orders"
                        buy = {
                            "instrument_id": instrument_id,
                            "client_order_id": str(uuid4()),
                            "side": "buy",
                            "quantity": 10,
                        }
                        denied = await http.post(order_path, json=buy)
                        assert denied.status_code == 400 and "WLS" in denied.text
                        universe = {
                            "source_url": "https://example.org/wls",
                            "observed_at": datetime.now(UTC),
                            "content_hash": "0" * 64,
                            "records": [
                                {
                                    "security_id": "fixture",
                                    "symbol": symbol,
                                    "exchange": "XTST",
                                    "asset_class": "equity",
                                    "as_of": day(1),
                                }
                            ],
                        }
                        await session.execute(
                            insert(EntityRegistry)
                            .values(name="wls_universe", **universe)
                            .on_conflict_do_update(
                                index_elements=[EntityRegistry.name], set_=universe
                            )
                        )
                        await session.commit()
                        denied = await http.post(order_path, json=buy)
                        assert denied.status_code == 400 and "Conversion" in denied.text
                        await http.post("/api/v1/market/fx-rates", json={**fx, "as_of": day(8)})
                        denied = await http.post(order_path, json=buy)
                        assert denied.status_code == 400 and "Conversion" in denied.text

                        # All amounts, fees and cash are USD, while the local quote stays 100 HKD.
                        good_fx = {**fx, "as_of": day(1), "usd_per_unit": "0.125"}
                        await http.post("/api/v1/market/fx-rates", json=good_fx)
                        bought = await http.post(order_path, json=buy)
                        assert bought.status_code == 200, bought.text
                        trade = bought.json()
                        assert Decimal(trade["price"]) == Decimal("12.5")
                        assert Decimal(trade["fee"]) == Decimal("0.13")
                        assert trade["conversion"]["local_close"] == "100.000000"
                        assert trade["conversion"]["usd_per_unit"] == "0.1250000000"
                        assert trade["conversion"]["quote_provider"] == "manual"
                        assert trade["conversion"]["quote_context"]["currency"] == "HKD"
                        assert trade["conversion"]["quote_context"]["provider_symbol"] is None
                        await http.post(
                            "/api/v1/market/fx-rates", json={**good_fx, "usd_per_unit": "0.13"}
                        )
                        replay = (await http.post(order_path, json=buy)).json()
                        assert (
                            replay["id"] == trade["id"]
                            and replay["conversion"] == trade["conversion"]
                        )
                        snapshot = (
                            await http.get(f"/api/v1/market/portfolios/{portfolio_id}")
                        ).json()
                        assert Decimal(snapshot["total_pnl"]) == Decimal("4.87")
                        assert Decimal(snapshot["positions"][0]["value"]) == Decimal("130")
                        await http.post(price_path, json={**price, "close": "120"})
                        sold = (
                            await http.post(
                                order_path,
                                json={**buy, "client_order_id": str(uuid4()), "side": "sell"},
                            )
                        ).json()
                        assert Decimal(sold["realized_pnl"]) == Decimal("30.71")

                        calls = []

                        def handler(request):
                            calls.append(request.url.params["symbol"])
                            return httpx.Response(200, json={})

                        await MarketDataService(session).collect(
                            AlphaVantageClient(
                                "fixture-key", transport=httpx.MockTransport(handler)
                            ),
                            limit=1,
                        )
                        assert symbol not in calls, (
                            "Manual international listings must not consume the US collector quota"
                        )
                        assert (
                            await session.execute(
                                select(MarketInstrument).where(MarketInstrument.id == instrument_id)
                            )
                        ).scalar_one().cik is None
                finally:
                    app.dependency_overrides.pop(get_db_session, None)
                print(
                    "International smoke passed: identities, local units, FX date/age, WLS gate, "
                    "USD fees/P&L, immutable evidence, collector isolation"
                )
        finally:
            await outer.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
