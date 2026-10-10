from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from app.collectors.international import AirbusPressCollector
from app.core.config import Settings
from app.schemas.workspace import BenchmarkInput, DataBatch, ProfileInput
from app.services.access import access_guard, check_origin, password_hash, password_matches, token_hash
from app.services.portfolio_report import allocation, benchmark_comparison


def request(method="GET", path="/api/v1/market/instruments", origin="http://localhost:3000"):
    return Request({"type": "http", "method": method, "path": path, "query_string": b"",
                    "scheme": "http", "server": ("localhost", 8000),
                    "headers": [(b"origin", origin.encode())]})


def test_password_hash_unique_salts_and_verification():
    a, b = password_hash("a long valid password"), password_hash("a long valid password")
    assert a != b
    assert password_matches("a long valid password", a)
    assert not password_matches("wrong", a)
    assert not password_matches("wrong", "invalid")
    assert len(token_hash("opaque token")) == 64


def test_production_requires_auth_and_https_cookies():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")
    assert Settings(_env_file=None, environment="production", auth_enabled=True, auth_cookie_secure=True)


@pytest.mark.asyncio
async def test_local_access_preserves_existing_behavior(monkeypatch):
    monkeypatch.setattr("app.services.access.get_settings", lambda: SimpleNamespace(auth_enabled=False))
    r = request("POST")
    await access_guard(r, None)
    assert r.state.role == "admin" and r.state.actor == "local"


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,role,expected", [
    ("GET", "/api/v1/market/instruments", "viewer", None),
    ("POST", "/api/v1/market/portfolios", "viewer", 403),
    ("POST", "/api/v1/workspace/alerts/abc/read", "viewer", None),
    ("POST", "/api/v1/market/portfolios", "editor", None),
])
async def test_access_roles(monkeypatch, method, path, role, expected):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("app.services.access.get_settings", lambda: SimpleNamespace(
        auth_enabled=True, cors_origins=["http://localhost:3000"]))
    monkeypatch.setattr("app.services.access.current_user", AsyncMock(return_value=SimpleNamespace(id=uuid4(), role=role)))
    if expected:
        with pytest.raises(HTTPException) as exc:
            await access_guard(request(method, path), None)
        assert exc.value.status_code == expected
    else:
        await access_guard(request(method, path), None)


@pytest.mark.asyncio
async def test_missing_session_rejected(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("app.services.access.get_settings", lambda: SimpleNamespace(auth_enabled=True))
    monkeypatch.setattr("app.services.access.current_user", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await access_guard(request(), None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("result,expected", [(21, 429), (OSError("unavailable"), 503)])
async def test_login_rate_limit_and_dependency_failure(monkeypatch, result, expected):
    from unittest.mock import AsyncMock, MagicMock
    from app.api.routes.access import limit_login
    redis = SimpleNamespace(eval=AsyncMock(side_effect=result if isinstance(result, Exception) else None,
                                          return_value=result))
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=redis)
    client.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("app.api.routes.access.Redis.from_url", lambda _: client)
    with pytest.raises(HTTPException) as exc:
        await limit_login(request(), "qa-user")
    assert exc.value.status_code == expected


def test_cross_site_write_rejected():
    with pytest.raises(HTTPException) as exc:
        check_origin(request("POST", origin="https://foreign.example"))
    assert exc.value.status_code == 403


def snapshot(value=Decimal(100), stale=False):
    return {"total_value": value, "valuation_stale": stale, "cash": Decimal(40), "positions": [
        {"instrument_id": "one", "symbol": "QA", "exchange": "XPAR", "currency": "EUR", "value": Decimal(60)},
    ]}


def test_allocation_includes_cash_and_preserves_unknown_classifications():
    result = allocation(snapshot(), {})
    assert result["sector"][0]["label"] == "Non documenté"
    assert result["country"][0]["label"] == "Non documenté"
    assert result["currency"][0]["weight_pct"] == Decimal(60)
    assert result["cash"]["weight_pct"] == Decimal(40)


@pytest.mark.parametrize("value,stale", [(None, False), (Decimal(100), True)])
def test_allocation_blocks_weights_when_incomplete_or_stale(value, stale):
    result = allocation(snapshot(value, stale), {})
    assert result["security"][0]["weight_pct"] is None
    assert result["cash"]["weight_pct"] is None


def test_comparison_exact_dates_and_price_index_difference_blocked():
    history = [{"date": "2026-01-01", "status": "available", "total_value": "100"},
               {"date": "2026-01-03", "status": "available", "total_value": "120"}]
    points = [SimpleNamespace(session_date=d, data={"level": level, "convention": "price"})
              for d, level in [("2026-01-01", "100"), ("2026-01-03", "110")]]
    result = benchmark_comparison(history, points)
    assert result["portfolio_pct"] == Decimal(20)
    assert result["benchmark_pct"] == Decimal(10)
    assert result["difference_pp"] is None
    assert benchmark_comparison(history, points[:1])["status"] == "unavailable"
    history[-1]["status"] = "stale"
    assert benchmark_comparison(history, points)["status"] == "unavailable"


def test_import_rejects_ambiguous_record_or_fake_confirmation():
    with pytest.raises(ValidationError):
        DataBatch.model_validate({"items": [{"kind": "something", "instrument_id": str(uuid4())}]})
    with pytest.raises(ValidationError):
        ProfileInput.model_validate({"sector": "Finance", "country": "FR", "as_of": "2026-01-01",
            "source_url": "https://example.org/proof", "published_at": "2026-01-01T10:00:00Z",
            "note": "Classification explicitement documentée", "confirmed": False})


def test_benchmark_rejects_future_session_and_secret_source():
    data = {"series": "QA", "name": "Test", "currency": "USD", "convention": "net_total_return",
            "session_date": "2026-02-01", "level": "100", "published_at": "2026-01-01T10:00:00Z",
            "source_url": "https://example.org/proof", "note": "Source des niveaux exacts de l’indice", "confirmed": True}
    with pytest.raises(ValidationError):
        BenchmarkInput.model_validate(data)
    data["session_date"] = "2026-01-01"
    data["source_url"] = "https://example.org/proof?apikey=secret"
    with pytest.raises(ValidationError):
        BenchmarkInput.model_validate(data)


@pytest.mark.asyncio
async def test_international_feed_limits_and_redirects():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        302, headers={"Location": "http://127.0.0.1/private"}))) as client:
        with pytest.raises(ValueError, match="domaine officiel"):
            await AirbusPressCollector(client).fetch()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, content=b"x" * 100))) as client:
        collector = AirbusPressCollector(client)
        collector.max_bytes = 10
        with pytest.raises(ValueError, match="volumineux"):
            await collector.fetch()


def test_feed_preserves_published_date_and_rejects_foreign_links():
    feed = b'''<rss version="2.0"><channel><title>QA</title>
    <item><title>Good</title><link>https://www.airbus.com/en/newsroom/one</link><pubDate>Thu, 01 Jan 2026 10:00:00 GMT</pubDate><description>Excerpt</description></item>
    <item><title>Bad</title><link>https://other.example/one</link></item></channel></rss>'''
    rows = AirbusPressCollector().normalize(feed)
    assert len(rows) == 1 and rows[0].published_at == datetime(2026, 1, 1, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_wls_scheduler_actually_runs_its_collector(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from app.scheduler.main import run_wls_identity_collector
    monkeypatch.setattr("app.scheduler.main.get_settings", lambda: SimpleNamespace(scheduler_run_on_start=True))
    collector = SimpleNamespace(collect=AsyncMock(return_value={"attempted": 1}))
    monkeypatch.setattr("app.scheduler.main.WlsAutomationService", lambda _: collector)
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=object())
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr("app.scheduler.main.async_session_factory", factory)
    monkeypatch.setattr("app.scheduler.main.asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await run_wls_identity_collector()
    collector.collect.assert_awaited_once()
