"""Scoped bearer authentication, deliberately independent of browser sessions."""
import hashlib
import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.semantic_analysis import PassageExtraction
from app.semantic.prompt import PROMPT_VERSION
from app.services.remote_ai import RemoteAiService


async def worker_access(request: Request):
    settings = get_settings()
    authorization = request.headers.get("authorization", "")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    expected = settings.ai_worker_token_sha256.get_secret_value()
    if not authorization.startswith("Bearer ") or not expected or not hmac.compare_digest(digest, expected):
        raise HTTPException(401, "Worker credential required")
    if settings.ai_execution_mode != "remote" or not settings.ai_analysis_enabled:
        raise HTTPException(503, "Remote analysis disabled")


router = APIRouter(dependencies=[Depends(worker_access)])
Db = Annotated[object, Depends(get_db_session)]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=80)


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_id: UUID
    extraction: PassageExtraction | None = None
    prompt_tokens: int | None = Field(default=None, ge=0, le=1000000)
    completion_tokens: int | None = Field(default=None, ge=0, le=1000000)
    error_code: str | None = Field(default=None, pattern=r"^(ollama_failed|invalid_output|worker_failed)$")

    @model_validator(mode="after")
    def outcome(self):
        if (self.extraction is None) == (self.error_code is None):
            raise ValueError("Supply either extraction or error_code")
        return self


async def bounded_body(request, schema, limit):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise HTTPException(413, "Worker payload too large")
    try:
        return schema.model_validate_json(bytes(body))
    except ValidationError:
        raise HTTPException(422, "Invalid worker payload") from None


@router.post("/claim")
async def claim(request: Request, session: Db):
    data = await bounded_body(request, Claim, 2048)
    settings = get_settings()
    if data.model != settings.ollama_model or data.prompt_version != PROMPT_VERSION:
        raise HTTPException(409, "Worker model or prompt version differs; update worker configuration/code")
    task = await RemoteAiService(session).claim(data.model, settings.ollama_timeout_seconds)
    await session.commit()
    return {"task": task}


@router.post("/heartbeat")
async def heartbeat(request: Request, session: Db):
    data = await bounded_body(request, Claim, 2048)
    if data.model != get_settings().ollama_model or data.prompt_version != PROMPT_VERSION:
        raise HTTPException(409, "Worker model or prompt version differs")
    await RemoteAiService(session).heartbeat(data.model)
    await session.commit()
    return {"accepted": True}


@router.post("/{identifier}/complete")
async def complete(identifier: UUID, request: Request, session: Db):
    data = await bounded_body(request, Completion, 100000)
    try:
        await RemoteAiService(session).complete(identifier, data.lease_id, data.extraction,
            data.prompt_tokens, data.completion_tokens, data.error_code)
        await session.commit()
    except ValueError:
        await session.rollback()
        raise HTTPException(409, "Stale lease or evidence absent from assigned source") from None
    return {"accepted": True}
