"""Server administration only; never runs inside the local worker."""
import argparse
import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.ai_task import AiTask
from app.services.remote_ai import RemoteAiService


async def main(identifier):
    async with async_session_factory() as session:
        if identifier:
            task = (await session.execute(select(AiTask).where(AiTask.id == identifier)
                .with_for_update())).scalar_one_or_none()
            if task is None or task.status != "failed":
                raise SystemExit("Only a known failed task may be retried")
            task.status, task.attempts = "pending", 0
            task.lease_id = task.lease_until = task.finished_at = task.error_code = None
            task.available_at = datetime.now(UTC)
            await session.commit()
            print("Failed task explicitly requeued")
        settings = get_settings()
        print(await RemoteAiService(session).status(settings.ai_analysis_enabled, settings.ai_execution_mode))
        rows = (await session.execute(select(AiTask.id, AiTask.status, AiTask.error_code)
            .where(AiTask.status == "failed").limit(20))).all()
        for row in rows:
            print(row.id, row.status, row.error_code)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-failed", type=UUID)
    asyncio.run(main(parser.parse_args().retry_failed))
