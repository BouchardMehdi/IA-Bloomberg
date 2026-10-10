"""API/PostgreSQL assertions; no network; every fixture rolled back."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, get_db_session
from app.main import app
from app.market.alpha_vantage import AlphaVantageClient
from app.models.market import DailyPrice, FxRate, MarketFetchRun, MarketInstrument
from app.models.portfolio import PaperPortfolio, PaperPosition, PaperTrade
from app.models.portfolio_tracking import PortfolioObservation
from app.services.market_data import MarketDataService
from tests.test_valuation import payload


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
                today = now.date()
                instrument = MarketInstrument(
                    symbol="QA" + uuid4().hex[:8].upper(),
                    exchange="XPAR",
                    currency="EUR",
                    quote_multiplier=Decimal("1"),
                    name="Tracking fixture",
                    price_provider="manual",
                    registry_url="https://example.org/identity",
                    registry_observed_at=now,
                )
                session.add(instrument)
                await session.flush()
                instrument_id = instrument.id
                price = DailyPrice(
                    instrument_id=instrument_id,
                    session_date=today,
                    close=Decimal("25"),
                    volume=100,
                    source_url="https://example.org/price",
                    fetched_at=now,
                    provider="manual",
                )
                fx = (
                    await session.execute(
                        select(FxRate).where(FxRate.currency == "EUR", FxRate.rate_date == today)
                    )
                ).scalar_one_or_none()
                session.add(price)
                if fx is None:
                    fx = FxRate(
                        currency="EUR",
                        rate_date=today,
                        usd_per_unit=Decimal("2"),
                        source_url="https://example.org/fx",
                        fetched_at=now,
                        provider="manual",
                    )
                    session.add(fx)
                # Use a deterministic fixture FX even if a live ECB observation exists.
                fx.usd_per_unit = Decimal("2")
                await session.commit()
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    root = "/api/v1/market"
                    created = await client.post(
                        root + "/portfolios", json={"name": "Tracking fixture", "fee_bps": "0"}
                    )
                    assert created.status_code == 201, created.text
                    pid = created.json()["id"]
                    portfolio = await session.get(PaperPortfolio, UUID(pid))
                    portfolio.cash -= Decimal("1000")
                    session.add_all(
                        [
                            PaperPosition(
                                portfolio_id=portfolio.id,
                                instrument_id=instrument_id,
                                quantity=10,
                                cost_basis=Decimal("1000"),
                            ),
                            PaperTrade(
                                portfolio_id=portfolio.id,
                                instrument_id=instrument_id,
                                client_order_id=uuid4(),
                                side="buy",
                                quantity=10,
                                price=Decimal("100"),
                                fee=Decimal("0"),
                                realized_pnl=Decimal("0"),
                                quote_date=today - timedelta(days=3),
                                quote_source_url="https://example.org/old-price",
                                executed_at=now - timedelta(days=3),
                            ),
                        ]
                    )
                    await session.commit()
                    path = f"{root}/portfolios/{pid}"
                    first = await client.post(path + "/history")
                    assert first.status_code == 200
                    same = await client.post(path + "/history")
                    assert not same.json()["inserted"], same.text
                    hist = (await client.get(path + "/history")).json()
                    assert len(hist["items"]) == 1
                    evidence_before = hist["items"][0]
                    observation_id = evidence_before["id"]
                    dividend = {
                        "kind": "dividend",
                        "effective_date": (today - timedelta(days=1)).isoformat(),
                        "payment_date": today.isoformat(),
                        "currency": "EUR",
                        "net_amount_per_security": "2",
                        "source_url": "https://example.org/dividend",
                        "published_at": (now - timedelta(days=2)).isoformat(),
                        "note": "Montant net par titre EUR et cotation explicitement documentés.",
                        "confirmed": True,
                    }
                    action_path = path + f"/actions/{instrument_id}"
                    result = await client.post(action_path, json=dividend)
                    assert result.status_code == 200, result.text
                    assert result.json()["cash_delta"] == "40.00"
                    assert not (await client.post(action_path, json=dividend)).json()["inserted"]
                    assert (
                        await client.post(
                            action_path, json=dividend | {"net_amount_per_security": "3"}
                        )
                    ).status_code == 400
                    split = {
                        "kind": "split",
                        "effective_date": today.isoformat(),
                        "numerator": 2,
                        "denominator": 1,
                        "source_url": "https://example.org/split",
                        "published_at": (now - timedelta(days=2)).isoformat(),
                        "note": "Division de deux titres nouveaux pour un ancien, cotation exacte.",
                        "confirmed": True,
                    }
                    result = await client.post(action_path, json=split)
                    assert result.status_code == 200, result.text
                    snapshot = (await client.get(path)).json()
                    assert snapshot["positions"][0]["quantity"] == 20
                    assert snapshot["positions"][0]["cost_basis"] == "1000.00"
                    assert snapshot["dividend_income"] == "40.00"
                    assert snapshot["total_value"] == "1000040.00"
                    replay = await client.post(action_path, json=split)
                    assert not replay.json()["inserted"]
                    sold = await client.post(
                        path + "/orders",
                        json={
                            "instrument_id": str(instrument_id),
                            "client_order_id": str(uuid4()),
                            "side": "sell",
                            "quantity": 5,
                        },
                    )
                    assert sold.status_code == 200, sold.text
                    ambiguous = await client.post(
                        action_path, json=dividend | {"effective_date": today.isoformat()}
                    )
                    assert ambiguous.status_code == 400
                    old = await session.get(PortfolioObservation, UUID(observation_id))
                    assert old.data["positions"][0]["quantity"] == 10
                    # Corrected source data cannot rewrite an old snapshot.
                    price.close = Decimal("30")
                    await session.commit()
                    await client.post(path + "/history")
                    assert Decimal(old.data["positions"][0]["price"]) == Decimal("25")
                    # Missing FX creates an explicit gap, never an invented USD value.
                    await session.execute(delete(FxRate).where(FxRate.currency == "EUR"))
                    await session.commit()
                    await client.post(path + "/history")
                    hist = (await client.get(path + "/history")).json()
                    assert hist["items"][0]["status"] == "missing"
                    assert hist["items"][0]["total_value"] is None
                    # Restore known FX before exercising mapped collection.
                    session.add(
                        FxRate(
                            currency="EUR",
                            rate_date=today,
                            usd_per_unit=Decimal("2"),
                            source_url="https://example.org/fx",
                            fetched_at=now,
                            provider="manual",
                        )
                    )
                    await session.commit()
                    mapping = {
                        "instrument_id": str(instrument_id),
                        "symbol": instrument.symbol,
                        "exchange": "XPAR",
                        "currency": "EUR",
                        "quote_multiplier": "1",
                        "provider_symbol": "EX.PAR",
                        "source_url": "https://example.org/provider-identity",
                        "published_at": (now - timedelta(days=2)).isoformat(),
                        "as_of": today.isoformat(),
                        "note": "Symbole exact, MIC, devise EUR et unité majeure documentés.",
                        "confirmed": True,
                    }
                    result = await client.post(root + "/price-mappings", json=mapping)
                    assert result.status_code == 200, result.text
                    assert (
                        await client.post(
                            root + "/price-mappings", json=mapping | {"currency": "GBP"}
                        )
                    ).status_code == 400
                    # Isolate shared reservations within the rolled-back transaction.
                    await session.execute(delete(MarketFetchRun))
                    await session.execute(
                        update(MarketInstrument)
                        .where(MarketInstrument.id != instrument_id)
                        .values(price_provider="manual")
                    )
                    await session.commit()

                    def respond(request):
                        assert request.url.params["symbol"] == "EX.PAR"
                        return httpx.Response(
                            200,
                            json={
                                "Meta Data": {"2. Symbol": "EX.PAR"},
                                "Time Series (Daily)": {
                                    today.isoformat(): {"4. close": "32", "5. volume": "50"}
                                },
                            },
                        )

                    provider = AlphaVantageClient("fixture", transport=httpx.MockTransport(respond))
                    stats = await MarketDataService(session).collect(provider, limit=1)
                    assert stats["success"] == 1, stats
                    fresh = await MarketDataService(session).latest_price(instrument_id)
                    await session.refresh(fresh)
                    assert fresh.quote_context["mapping_evidence"]["provider_symbol"] == "EX.PAR"
                    coverage = await client.get(root + "/coverage")
                    assert coverage.status_code == 200, coverage.text
                    row = next(
                        r
                        for r in coverage.json()["items"]
                        if r["instrument_id"] == str(instrument_id)
                    )
                    assert row["usd_status"] == "available"
                    assert "valuation_blocked" in row["missing"]
                    batch = {
                        "items": [
                            {
                                "instrument_id": str(instrument_id),
                                "observation": payload(
                                    currency="EUR", valuation_date=today.isoformat()
                                ),
                            },
                            {"instrument_id": str(uuid4()), "observation": payload(currency="EUR")},
                        ]
                    }
                    imported = await client.post(root + "/valuations/batch", json=batch)
                    assert imported.status_code == 200, imported.text
                    assert imported.json()["saved_count"] == 1
                    assert imported.json()["items"][1]["status"] == "rejected"
                    repeated = await client.post(root + "/valuations/batch", json=batch)
                    assert not repeated.json()["items"][0]["inserted"]
                    valuation = (
                        await client.get(root + f"/instruments/{instrument_id}/valuation")
                    ).json()
                    assert valuation["calculation"]["status"] == "available", valuation
                    assert (
                        await client.get(
                            root + f"/instruments/{instrument_id}/valuation-preparation"
                        )
                    ).status_code == 200
                    assert (
                        await client.post(root + "/valuations/batch", json={"items": []})
                    ).status_code == 422
                print("Portfolio tracking smoke passed (all fixtures rolled back).")
            finally:
                app.dependency_overrides.clear()
                await session.rollback()
                await transaction.rollback()


if __name__ == "__main__":
    asyncio.run(main())
