import asyncio
import hashlib
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.workspace import WorkspaceSession, WorkspaceUser
from app.services.access import (
    COOKIE, check_origin, current_user, issue_session, password_hash,
    password_matches, require_admin, token_hash,
)

router = APIRouter()
Db = Annotated[object, Depends(get_db_session)]
DUMMY_PASSWORD_HASH = password_hash("not-a-real-user")


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[a-z0-9_.-]{3,80}$")
    password: str = Field(min_length=1, max_length=256)


class UserCreate(Login):
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "editor", "viewer"]


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    role: Literal["admin", "editor", "viewer"]


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def public_user(user):
    return {"id": str(user.id), "username": user.username, "role": user.role,
            "enabled": user.enabled}


@router.get("/me")
async def me(request: Request, session: Db):
    enabled = get_settings().auth_enabled
    user = await current_user(request, session) if enabled else None
    return {"auth_enabled": enabled, "user": public_user(user) if user else None}


async def limit_login(request, username):
    # Fixed windows, shared by backend processes; failures of Redis fail closed.
    host = request.client.host if request.client else "unknown"
    keys = ["auth:ip:" + hashlib.sha256(host.encode()).hexdigest(), "auth:user:" + username]
    try:
        async with Redis.from_url(get_settings().redis_url) as redis:
            for key in keys:
                attempts = await redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                    1, key, 900,
                )
                if attempts > 20:
                    raise HTTPException(429, "Trop de tentatives. Réessayer dans 15 minutes.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Connexion momentanément indisponible.") from None


@router.post("/login")
async def login(data: Login, request: Request, response: Response, session: Db):
    if not get_settings().auth_enabled:
        raise HTTPException(400, "L’authentification n’est pas activée.")
    check_origin(request)
    await limit_login(request, data.username)
    user = (await session.execute(select(WorkspaceUser).where(
        WorkspaceUser.username == data.username))).scalar_one_or_none()
    # Perform a real KDF even for an unknown account.
    encoded = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid = await asyncio.to_thread(password_matches, data.password, encoded)
    if not user or not user.enabled or not valid:
        raise HTTPException(401, "Identifiants incorrects.")
    token = await issue_session(session, user)
    response.set_cookie(COOKIE, token, httponly=True, secure=get_settings().auth_cookie_secure,
                        samesite="strict", max_age=43200, path="/")
    response.headers["Cache-Control"] = "no-store"
    return public_user(user)


@router.post("/logout")
async def logout(request: Request, response: Response, session: Db):
    await session.execute(delete(WorkspaceSession).where(
        WorkspaceSession.token_hash == token_hash(request.cookies.get(COOKIE, ""))))
    await session.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
async def change_password(data: PasswordChange, request: Request, session: Db):
    user = await current_user(request, session)
    if not user or not await asyncio.to_thread(password_matches, data.current_password, user.password_hash):
        raise HTTPException(403, "Mot de passe actuel incorrect.")
    user.password_hash = await asyncio.to_thread(password_hash, data.new_password)
    await session.execute(delete(WorkspaceSession).where(WorkspaceSession.user_id == user.id))
    await session.commit()
    return {"ok": True, "notice": "Mot de passe changé. Reconnexion requise sur tous les appareils."}


@router.get("/users", dependencies=[Depends(require_admin)])
async def users(session: Db):
    return {"items": [public_user(u) for u in (await session.execute(
        select(WorkspaceUser).order_by(WorkspaceUser.username))).scalars()]}


@router.post("/users", dependencies=[Depends(require_admin)])
async def create_user(data: UserCreate, session: Db):
    user = WorkspaceUser(username=data.username, role=data.role, enabled=True,
                         password_hash=await asyncio.to_thread(password_hash, data.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Ce nom de compte existe déjà.") from None
    return public_user(user)


@router.patch("/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(user_id: UUID, data: UserUpdate, session: Db):
    await session.execute(select(func.pg_advisory_xact_lock(721930)))
    user = await session.get(WorkspaceUser, user_id)
    if not user:
        raise HTTPException(404, "Compte introuvable.")
    admins = (await session.execute(select(func.count()).select_from(WorkspaceUser).where(
        WorkspaceUser.role == "admin", WorkspaceUser.enabled.is_(True)))).scalar_one()
    if user.enabled and user.role == "admin" and admins <= 1 and (not data.enabled or data.role != "admin"):
        raise HTTPException(400, "Conserver au moins un administrateur actif.")
    user.role, user.enabled = data.role, data.enabled
    await session.execute(delete(WorkspaceSession).where(WorkspaceSession.user_id == user.id))
    await session.commit()
    return public_user(user)
