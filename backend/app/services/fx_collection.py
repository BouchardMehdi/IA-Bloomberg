from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.market.ecb_fx import SOURCE_URL, EcbFxClient, FxCollectionError
from app.models.market import FxCollectionRun, FxRate


def run_read(run) -> dict | None:
    if run is None:
        return None
    return {
        key: getattr(run, key)
        for key in (
            "id",
            "started_at",
            "finished_at",
            "status",
            "error_code",
            "source_url",
            "latest_reference_date",
            "record_count",
            "preserved_manual_count",
            "available_currencies",
        )
    }


class FxCollectionService:
    def __init__(self, session):
        self.session = session

    async def status(self) -> dict:
        query = select(FxCollectionRun).order_by(FxCollectionRun.started_at.desc()).limit(1)
        latest = (await self.session.execute(query)).scalar_one_or_none()
        success = (
            await self.session.execute(query.where(FxCollectionRun.status == "success"))
        ).scalar_one_or_none()
        return {
            "enabled": get_settings().fx_collection_enabled,
            "interval_minutes": get_settings().fx_collection_interval_minutes,
            "latest_run": run_read(latest),
            "last_success": run_read(success),
            "source_url": SOURCE_URL,
        }

    async def collect(self, client: EcbFxClient) -> dict:
        # Lock covers the bounded HTTP call and atomic batch write across processes.
        await self.session.execute(select(func.pg_advisory_xact_lock(721904)))
        now = datetime.now(UTC)
        previous = (
            await self.session.execute(
                select(FxCollectionRun).order_by(FxCollectionRun.started_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        interval = get_settings().fx_collection_interval_minutes
        if previous and previous.started_at > now - timedelta(minutes=interval):
            await self.session.commit()
            return {"status": "skipped", "reason": "cached_attempt"}
        run = FxCollectionRun(started_at=now, status="running", source_url=SOURCE_URL)
        self.session.add(run)
        try:
            records = await client.fetch()
        except FxCollectionError as exc:
            run.status = "failed"
            run.error_code = str(exc)
        else:
            values = [
                {**r, "provider": "ecb", "source_url": SOURCE_URL, "fetched_at": now}
                for r in records
            ]
            statement = insert(FxRate).values(values)
            written = (
                (
                    await self.session.execute(
                        statement.on_conflict_do_update(
                            constraint="uq_fx_currency_date",
                            set_={
                                key: statement.excluded[key]
                                for key in (
                                    "usd_per_unit",
                                    "derivation",
                                    "provider",
                                    "source_url",
                                    "fetched_at",
                                )
                            },
                            where=FxRate.provider == "ecb",
                        ).returning(FxRate.id)
                    )
                )
                .scalars()
                .all()
            )
            run.preserved_manual_count = len(records) - len(written)
            run.status = "success"
            run.record_count = len(records)
            run.latest_reference_date = max(r["rate_date"] for r in records)
            run.available_currencies = sorted(
                {r["currency"] for r in records if r["rate_date"] == run.latest_reference_date}
            )
        run.finished_at = datetime.now(UTC)
        await self.session.commit()
        return run_read(run)
