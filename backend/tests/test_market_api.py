from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_simulation_api_rejects_fractional_negative_and_short_order_requests():
    endpoint = f"/api/v1/market/portfolios/{uuid4()}/orders"
    base = {
        "instrument_id": str(uuid4()),
        "client_order_id": str(uuid4()),
        "side": "buy",
        "quantity": 1,
    }
    for changes in ({"quantity": -1}, {"quantity": 1.5}, {"side": "short"}):
        assert client.post(endpoint, json={**base, **changes}).status_code == 422


def test_simulation_api_rejects_unsupported_currency_and_malformed_dates():
    for extra in ({"currency": "EUR"}, {"starts_on": "not-a-date"}, {"initial_capital": -100}):
        assert (
            client.post("/api/v1/market/portfolios", json={"name": "Fixture", **extra}).status_code
            == 422
        )


def test_market_api_rejects_unvalidated_symbols_and_excessive_history_requests():
    assert (
        client.post("/api/v1/market/instruments", json={"symbol": "EX&apikey=test"}).status_code
        == 422
    )
    assert client.get(f"/api/v1/market/instruments/{uuid4()}/prices?limit=1001").status_code == 422
