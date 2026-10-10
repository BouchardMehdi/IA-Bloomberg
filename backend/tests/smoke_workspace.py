"""Integration checks for workspace changes; run on the isolated QA database."""
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import engine, get_db_session
from app.main import app
from app.models.article import Article
from app.models.collection_run import CollectionRun
from app.models.event import Event, EventArticle
from app.models.market import MarketInstrument
from app.models.portfolio import PaperPortfolio
from app.models.source import Source
from app.models.workspace import DataProposal, WorkspaceSession, WorkspaceUser
from app.schemas.workspace import DataBatch
from app.services.access import password_hash
from app.services.alerts import AlertService
from app.services.data_import import DataImportService


async def main():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False,
                                join_transaction_mode="create_savepoint") as session:
            async def override():
                yield session
            app.dependency_overrides[get_db_session] = override
            try:
                now = datetime.now(UTC)
                instrument = MarketInstrument(symbol="QA", exchange="XPAR", name="QA only",
                    currency="EUR", quote_multiplier=Decimal(1), price_provider="manual",
                    registry_url="https://example.org/identity", registry_observed_at=now)
                source = Source(name="QA source", source_type="official_news", url="https://example.org/feed")
                session.add_all([instrument, source])
                await session.flush()
                article = Article(source_id=source.id, url="https://example.org/publication",
                    title="QA official publication", content="Declared feed excerpt", content_hash="a" * 64,
                    published_at=now - timedelta(days=1), fetched_at=now)
                session.add(article)
                await session.flush()
                event = Event(deduplication_key="QA:" + uuid4().hex, event_type="official_publication",
                    title=article.title, event_datetime=article.published_at, status="enriched")
                event.article_links.append(EventArticle(article_id=article.id, is_primary_source=True))
                session.add(event)
                session.add(CollectionRun(source_id=source.id, trigger="manual", status="failed",
                    started_at=now - timedelta(seconds=2), finished_at=now - timedelta(seconds=1)))
                await session.flush()
                service = AlertService(session)
                assert (await service.collect())["inserted"] == 2
                assert (await service.collect())["inserted"] == 0
                alerts = await service.detail("reader-one")
                assert alerts["unread_count"] == 2
                alert_id = alerts["items"][0]["id"]
                await service.mark_read("reader-one", alert_id)
                await service.mark_read("reader-one", alert_id)
                assert (await service.detail("reader-one"))["unread_count"] == 1
                assert (await service.detail("reader-two"))["unread_count"] == 2
                earnings = DataBatch.model_validate({"items": [{"kind": "earnings", "instrument_id": instrument.id,
                    "observation": {"kind": "reported", "fiscal_period_end": "2026-06-30", "report_date": "2026-08-01",
                        "period_type": "quarterly", "source_url": "https://example.org/results",
                        "published_at": "2026-08-01T10:00:00Z", "eps": "2.2", "currency": "EUR", "basis": "gaap_diluted"}}]})
                assert (await DataImportService(session).ingest(earnings))["items"][0]["result"]["inserted"]
                assert not (await DataImportService(session).ingest(earnings))["items"][0]["result"]["inserted"]
                proposal = DataBatch.model_validate({"items": [{"kind": "corporate_action", "instrument_id": instrument.id,
                    "observation": {"kind": "dividend", "effective_date": "2026-08-10", "payment_date": "2026-08-20",
                        "currency": "EUR", "net_amount_per_security": "1.5", "source_url": "https://example.org/dividend",
                        "published_at": "2026-08-01T10:00:00Z", "note": "Net dividend explicitly documented for this listing", "confirmed": True}}]})
                assert (await DataImportService(session).ingest(proposal))["items"][0]["result"]["proposal"]
                await DataImportService(session).ingest(proposal)
                assert (await session.execute(select(func.count()).select_from(DataProposal))).scalar_one() == 1
                assert (await session.execute(select(func.count()).select_from(PaperPortfolio))).scalar_one() == 0
                # The inbox advances beyond its first full batch; previously
                # processed files cannot starve the next file in the directory.
                import json
                import tempfile
                from contextlib import asynccontextmanager
                from pathlib import Path
                from app.services.data_inbox import process_inbox
                from app.models.workspace import WorkspaceCursor

                @asynccontextmanager
                async def fixture_factory():
                    yield session

                with tempfile.TemporaryDirectory() as directory, patch(
                    "app.services.data_inbox.async_session_factory", fixture_factory
                ):
                    for index in range(21):
                        data = earnings.model_dump(mode="json")
                        data["items"][0]["observation"]["source_url"] = f"https://example.org/result-{index}"
                        Path(directory, f"{index:02d}.json").write_text(json.dumps(data))
                    await process_inbox(directory)
                    query = select(func.count()).select_from(WorkspaceCursor).where(WorkspaceCursor.name.like("import:%"))
                    assert (await session.execute(query)).scalar_one() == 20
                    await process_inbox(directory)
                    assert (await session.execute(query)).scalar_one() == 21
                    await process_inbox(directory)
                    assert (await session.execute(query)).scalar_one() == 21
                    assert len(list(Path(directory).glob("*.json"))) == 21
                users = [WorkspaceUser(username=role, password_hash=password_hash("qa-password-only"), role=role, enabled=True)
                         for role in ("admin", "editor", "viewer")]
                session.add_all(users)
                await session.flush()
                settings = Settings(_env_file=None, auth_enabled=True, auth_cookie_secure=False)
                with patch("app.services.access.get_settings", return_value=settings), \
                     patch("app.api.routes.access.get_settings", return_value=settings), \
                     patch("app.api.routes.access.limit_login", AsyncMock()):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000",
                        headers={"Origin": "http://localhost:3000"}) as client:
                        assert (await client.get("/api/v1/workspace/alerts")).status_code == 401
                        assert (await client.post("/api/v1/auth/login", json={"username": "viewer", "password": "wrong"})).status_code == 401
                        response = await client.post("/api/v1/auth/login", json={"username": "viewer", "password": "qa-password-only"})
                        assert response.status_code == 200 and "HttpOnly" in response.headers["set-cookie"]
                        assert "SameSite=strict" in response.headers["set-cookie"]
                        assert (await client.get("/api/v1/workspace/alerts")).status_code == 200
                        assert (await client.post(f"/api/v1/workspace/alerts/{alert_id}/read", json={})).status_code == 200
                        assert (await client.post("/api/v1/workspace/imports", json={"items": []})).status_code == 403
                        assert (await client.post("/api/v1/workspace/journal", json={})).status_code == 403
                        assert (await client.get("/api/v1/auth/users")).status_code == 403
                        assert (await client.post("/api/v1/auth/logout", json={})).status_code == 200
                        assert (await client.get("/api/v1/workspace/alerts")).status_code == 401
                        assert (await client.post("/api/v1/auth/login", json={"username": "admin", "password": "qa-password-only"})).status_code == 200
                        assert (await client.patch(f"/api/v1/auth/users/{users[0].id}", json={"enabled": False, "role": "admin"})).status_code == 400
                        assert (await client.post("/api/v1/auth/users", headers={"Origin": "https://foreign.example"}, json={
                            "username": "evil", "password": "qa-password-only", "role": "admin"})).status_code == 403
                        assert (await client.post("/api/v1/auth/password", json={"current_password": "qa-password-only", "new_password": "qa-new-password-only"})).status_code == 200
                        assert (await client.get("/api/v1/workspace/alerts")).status_code == 401
                        assert (await client.post("/api/v1/auth/login", json={"username": "admin", "password": "qa-password-only"})).status_code == 401
                        assert (await client.post("/api/v1/auth/login", json={"username": "admin", "password": "qa-new-password-only"})).status_code == 200
                        stored = (await session.execute(select(WorkspaceSession))).scalars().all()
                        assert all(len(row.token_hash) == 64 for row in stored)
                        declaration = {"source_url": "https://example.org/index", "published_at": "2026-09-01T20:00:00Z",
                            "note": "Authorized index level for the exact USD series", "confirmed": True,
                            "series": "QA_USD", "name": "QA reference", "session_date": "2026-09-01", "level": "100",
                            "currency": "USD", "convention": "net_total_return"}
                        assert (await client.post("/api/v1/workspace/benchmarks", json=declaration)).status_code == 200
                        assert not (await client.post("/api/v1/workspace/benchmarks", json=declaration)).json()["inserted"]
                        assert (await client.post("/api/v1/workspace/benchmarks", json={**declaration, "level": "105"})).status_code == 400
                        assert (await client.post("/api/v1/workspace/benchmarks", json={**declaration, "convention": "price"})).status_code == 400
                        from tests.smoke_research_workspace import verify
                        await session.refresh(instrument)
                        await verify(session, client, instrument)
                print("Workspace PostgreSQL/API checks passed: sessions, roles, CSRF, revocation, last admin, alerts, receipts, imports, proposals and benchmark conflicts. Fixtures rolled back.")
            finally:
                app.dependency_overrides.clear()
                await session.close()
                await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
