"""Opt-in local directory of authorized structured exports, never a web crawler."""
import hashlib
import logging
from decimal import Decimal
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from app.db.session import async_session_factory
from app.models.workspace import WorkspaceCursor
from app.schemas.workspace import DataBatch
from app.services.data_import import DataImportService

logger = logging.getLogger(__name__)


async def process_inbox(directory):
    root = Path(directory).resolve(strict=True)
    processed = 0
    for path in sorted(root.glob("*.json"))[:1000]:
        if processed >= 20:
            break
        if path.is_symlink() or path.resolve().parent != root or path.stat().st_size > 1_000_000:
            continue
        payload = path.read_bytes()
        key = "import:" + hashlib.sha256(payload).hexdigest()[:32]
        async with async_session_factory() as session:
            from sqlalchemy import func, select
            await session.execute(select(func.pg_advisory_xact_lock(721933)))
            if await session.get(WorkspaceCursor, key):
                continue
            # A crashed run is retried safely: each observation/proposal is idempotent.
            try:
                request = DataBatch.model_validate_json(payload)
                result = await DataImportService(session).ingest(request)
            except ValueError:
                await session.rollback()
                result = {"error": "invalid_schema", "notice": "Fichier refusé : vérifier les schémas de l’API."}
            from sqlalchemy.dialects.postgresql import insert
            from datetime import UTC, datetime
            result = jsonable_encoder({**result, "processed_at": datetime.now(UTC).isoformat()},
                                      custom_encoder={Decimal: str})
            await session.execute(insert(WorkspaceCursor).values(name=key, data=result)
                .on_conflict_do_nothing())
            await session.commit()
            processed += 1
            logger.info("Authorized data inbox processed: hash=%s", key)
