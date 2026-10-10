"""Only the server owns persistence, task selection and evidence validation."""
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.models.ai_task import AiTask, AiWorkerState
from app.repositories.document_analysis import validate_passage_evidence
from app.semantic.prompt import PROMPT_VERSION

MAX_ATTEMPTS = 3


def task_fingerprint(model, source, title, text):
    value = json.dumps([PROMPT_VERSION, model, source, title, text], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


class RemoteAiService:
    def __init__(self, session):
        self.session = session

    async def enqueue(self, model, source, title, text):
        # These bounds match the existing passage planner and document limits.
        if len(text) > 6000 or len(title) > 10000 or len(source) > 1000:
            raise ValueError("Remote passage exceeds the permitted input budget")
        now = datetime.now(UTC)
        fingerprint = task_fingerprint(model, source, title, text)
        await self.session.execute(insert(AiTask).values(
            fingerprint=fingerprint, model_name=model, prompt_version=PROMPT_VERSION,
            source_name=source, title=title, input_text=text, status="pending", attempts=0,
            created_at=now, available_at=now,
        ).on_conflict_do_nothing(index_elements=[AiTask.fingerprint]))
        return (await self.session.execute(select(AiTask).where(
            AiTask.fingerprint == fingerprint))).scalar_one()

    async def heartbeat(self, model):
        now = datetime.now(UTC)
        await self.session.execute(insert(AiWorkerState).values(
            name="local", last_seen_at=now, model_name=model,
        ).on_conflict_do_update(index_elements=[AiWorkerState.name], set_={
            "last_seen_at": now, "model_name": model}))

    async def claim(self, model, timeout_seconds):
        now = datetime.now(UTC)
        # Expired final attempts become terminal, so a repeatedly stopped worker
        # cannot burn unbounded model time. An administrator may retry explicitly.
        await self.session.execute(update(AiTask).where(
            AiTask.status == "leased", AiTask.lease_until <= now,
            AiTask.attempts >= MAX_ATTEMPTS).values(
                status="failed", error_code="lease_expired", finished_at=now))
        task = (await self.session.execute(select(AiTask).where(
            AiTask.model_name == model, AiTask.prompt_version == PROMPT_VERSION,
            AiTask.attempts < MAX_ATTEMPTS,
            or_(and_(AiTask.status == "pending", AiTask.available_at <= now),
                and_(AiTask.status == "leased", AiTask.lease_until <= now)),
        ).order_by(AiTask.created_at, AiTask.id).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if task is None:
            return None
        task.status = "leased"
        task.lease_id = uuid.uuid4()
        task.lease_until = now + timedelta(seconds=timeout_seconds + 120)
        task.attempts += 1
        return {"id": task.id, "lease_id": task.lease_id, "model": task.model_name,
            "prompt_version": task.prompt_version, "source_name": task.source_name,
            "title": task.title, "content": task.input_text,
            "timeout_seconds": timeout_seconds, "lease_until": task.lease_until}

    async def complete(self, identifier, lease_id, extraction, prompt_tokens=None,
                       completion_tokens=None, error_code=None):
        task = (await self.session.execute(select(AiTask).where(
            AiTask.id == identifier).with_for_update())).scalar_one_or_none()
        now = datetime.now(UTC)
        if task is None or task.lease_id != lease_id:
            raise ValueError("Unknown or replaced lease")
        if task.status == "success":
            # A lost HTTP acknowledgement may safely be sent again, but the
            # accepted result is immutable and a different body is not accepted.
            if extraction is None or task.result != extraction.model_dump(mode="json"):
                raise ValueError("Result already accepted with different content")
            return
        if task.status != "leased" or task.lease_until <= now:
            raise ValueError("Expired or inactive lease")
        if extraction is not None:
            validate_passage_evidence(extraction, task.title, task.input_text)
            task.result = extraction.model_dump(mode="json")
            task.prompt_tokens, task.completion_tokens = prompt_tokens, completion_tokens
            task.status, task.finished_at, task.error_code = "success", now, None
        else:
            task.error_code = error_code or "worker_failed"
            task.status = "failed" if task.attempts >= MAX_ATTEMPTS else "pending"
            task.available_at = now + timedelta(minutes=10)
            task.finished_at = now if task.status == "failed" else None

    async def status(self, enabled, mode):
        counts = dict((await self.session.execute(select(AiTask.status, func.count())
            .group_by(AiTask.status))).all())
        worker = await self.session.get(AiWorkerState, "local")
        recent = bool(worker and worker.last_seen_at > datetime.now(UTC) - timedelta(minutes=2))
        return {"enabled": enabled, "mode": mode, "counts": counts,
            "last_seen_at": worker.last_seen_at if worker else None,
            "worker_status": "recent" if recent else "unconfirmed"}
