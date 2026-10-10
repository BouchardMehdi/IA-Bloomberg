"""Opaque, revocable sessions for a shared workspace (no public registration)."""
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.workspace import WorkspaceSession, WorkspaceUser

COOKIE = "market_ai_session"


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt${salt}${digest.hex()}"


def password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, _ = encoded.split("$")
        return algorithm == "scrypt" and hmac.compare_digest(password_hash(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def check_origin(request: Request):
    # Cookies alone never authorize a write from a foreign page.
    if request.headers.get("origin") not in get_settings().cors_origins:
        raise HTTPException(403, "Origine non autorisée pour cette modification.")


async def current_user(request: Request, session=Depends(get_db_session)):
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 200:
        return None
    return (await session.execute(
        select(WorkspaceUser).join(WorkspaceSession, WorkspaceSession.user_id == WorkspaceUser.id)
        .where(WorkspaceSession.token_hash == token_hash(token),
               WorkspaceSession.expires_at > datetime.now(UTC), WorkspaceUser.enabled.is_(True))
    )).scalar_one_or_none()


async def access_guard(request: Request, session=Depends(get_db_session)):
    settings = get_settings()
    if not settings.auth_enabled:
        request.state.actor = "local"
        request.state.role = "admin"
        return
    if request.url.path in {"/api/v1/health/live", "/api/v1/health/ready",
                            "/api/v1/auth/login", "/api/v1/auth/me"}:
        return
    user = await current_user(request, session)
    if user is None:
        raise HTTPException(401, "Connexion requise.")
    request.state.actor = str(user.id)
    request.state.role = user.role
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if user.role == "viewer" and request.url.path not in {
            "/api/v1/auth/logout", "/api/v1/auth/password",
        } and not request.url.path.endswith("/read"):
            raise HTTPException(403, "Ce compte dispose d’un accès en lecture seule.")


def require_admin(request: Request):
    if getattr(request.state, "role", None) != "admin":
        raise HTTPException(403, "Accès administrateur requis.")


async def issue_session(session, user):
    now = datetime.now(UTC)
    await session.execute(delete(WorkspaceSession).where(WorkspaceSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    session.add(WorkspaceSession(token_hash=token_hash(token), user_id=user.id,
                                 expires_at=now + timedelta(hours=12)))
    await session.commit()
    return token
