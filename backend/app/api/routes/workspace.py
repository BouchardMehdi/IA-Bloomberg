from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.routes.market import market_response
from app.db.session import get_db_session
from app.schemas.workspace import BenchmarkBatch, BenchmarkInput, DataBatch, ProfileInput
from app.services.alerts import AlertService
from app.services.data_import import DataImportService
from app.services.portfolio_report import PortfolioReportService

router = APIRouter()
Db = Annotated[object, Depends(get_db_session)]


async def perform(session, action):
    try:
        return market_response(await action)
    except (ValueError, LookupError) as exc:
        await session.rollback()
        raise HTTPException(404 if isinstance(exc, LookupError) else 400, str(exc)) from None


@router.get("/alerts")
async def alerts(request: Request, session: Db,
                 kind: Literal["publication", "extracted_fact", "calendar", "collection_error"] | None = None,
                 unread: bool = False, limit: int = Query(20, ge=1, le=100),
                 offset: int = Query(0, ge=0, le=1_000_000)):
    return market_response(await AlertService(session).detail(request.state.actor, kind, unread, limit, offset))


@router.post("/alerts/refresh")
async def refresh_alerts(session: Db):
    return market_response(await AlertService(session).collect())


@router.post("/alerts/{alert_id}/read")
async def read_alert(alert_id: UUID, request: Request, session: Db):
    return await perform(session, AlertService(session).mark_read(request.state.actor, alert_id))


@router.get("/portfolios/{portfolio_id}/report")
async def report(portfolio_id: UUID, session: Db, series: str | None = Query(None, max_length=100)):
    return await perform(session, PortfolioReportService(session).detail(portfolio_id, series))


@router.post("/instruments/{instrument_id}/profile")
async def profile(instrument_id: UUID, data: ProfileInput, session: Db):
    return await perform(session, PortfolioReportService(session).add_profile(instrument_id, data))


@router.post("/benchmarks")
async def benchmark(data: BenchmarkInput, session: Db):
    return await perform(session, PortfolioReportService(session).add_benchmark(data))


@router.post("/benchmarks/batch")
async def benchmark_batch(data: BenchmarkBatch, session: Db):
    results = []
    for index, point in enumerate(data.items):
        try:
            result = await PortfolioReportService(session).add_benchmark(point)
            results.append({"index": index, "status": "accepted", **result})
        except ValueError as exc:
            await session.rollback()
            results.append({"index": index, "status": "rejected", "error": str(exc)})
    return market_response({"items": results})


@router.post("/imports")
async def import_data(data: DataBatch, session: Db):
    return market_response(await DataImportService(session).ingest(data))


@router.get("/import-status")
async def import_status(session: Db):
    from sqlalchemy import select
    from app.models.workspace import WorkspaceCursor
    from app.core.config import get_settings
    rows = (await session.execute(select(WorkspaceCursor).where(
        WorkspaceCursor.name.like("import:%")).order_by(
            WorkspaceCursor.data["processed_at"].astext.desc().nulls_last()).limit(20))).scalars().all()
    return market_response({"enabled": bool(get_settings().data_inbox_directory),
                            "items": [{"hash": r.name[7:], **r.data} for r in rows]})


@router.get("/proposals")
async def proposals(session: Db, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return market_response(await DataImportService(session).proposals(limit, offset))


class ApplyProposal(BaseModel):
    portfolio_id: UUID
    confirmed: Literal[True]


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: UUID, data: ApplyProposal, session: Db):
    return await perform(session, DataImportService(session).apply(proposal_id, data.portfolio_id))
