"""Bootstrap/reset a local account without passing a password on the command line."""
import argparse
import asyncio
import getpass

from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.models.workspace import WorkspaceUser, WorkspaceSession
from app.services.access import password_hash


async def create(username, role, reset):
    import re
    if not re.fullmatch(r"[a-z0-9_.-]{3,80}", username):
        raise SystemExit("Nom : 3 à 80 lettres minuscules, chiffres, _, . ou -.")
    password = getpass.getpass("Mot de passe (12 caractères minimum) : ")
    if not 12 <= len(password) <= 256 or password != getpass.getpass("Confirmer : "):
        raise SystemExit("Mot de passe invalide ou confirmation différente.")
    async with async_session_factory() as session:
        user = (await session.execute(select(WorkspaceUser).where(
            WorkspaceUser.username == username))).scalar_one_or_none()
        if user and not reset:
            raise SystemExit("Compte existant. Utiliser --reset-password explicitement.")
        if user:
            user.password_hash = password_hash(password)
            await session.execute(delete(WorkspaceSession).where(WorkspaceSession.user_id == user.id))
        else:
            session.add(WorkspaceUser(username=username, role=role, enabled=True,
                                      password_hash=password_hash(password)))
        await session.commit()
    print("Compte enregistré. Aucun mot de passe affiché.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("username")
    p.add_argument("--role", choices=["admin", "editor", "viewer"], default="admin")
    p.add_argument("--reset-password", action="store_true")
    a = p.parse_args()
    asyncio.run(create(a.username, a.role, a.reset_password))
