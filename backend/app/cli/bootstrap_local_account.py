"""Create a first local admin, saving the generated password only in a private file."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import secrets

from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.workspace import WorkspaceUser
from app.services.access import password_hash


async def create(username, credential_file):
    if not re.fullmatch(r"[a-z0-9_.-]{3,80}", username):
        raise SystemExit("Identifiant invalide : minuscules, chiffres, _, . ou -, de 3 à 80 caractères.")
    path = Path(credential_file)
    async with async_session_factory() as session:
        existing = (await session.execute(select(WorkspaceUser).where(WorkspaceUser.username == username))).scalar_one_or_none()
        if existing:
            if not existing.enabled or existing.role != "admin":
                raise SystemExit("Le compte existant n’est pas administrateur actif. Aucune modification effectuée.")
            print("Administrateur existant conservé. Mot de passe inchangé.")
            return
        if path.exists():
            raise SystemExit("Le fichier privé existe déjà. Aucune clé ou donnée écrasée.")
        password = secrets.token_urlsafe(24)
        # Exclusive creation: never replace someone’s credentials.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"username": username, "password": password,
                "notice": "Accès local initial. Changez le mot de passe dans Mon espace et retirez ce fichier après conservation sûre."}, stream, ensure_ascii=False)
        session.add(WorkspaceUser(username=username, role="admin", enabled=True, password_hash=password_hash(password)))
        await session.commit()
    print("Administrateur créé. Identifiants disponibles uniquement dans le fichier privé fourni.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--credential-file", required=True)
    args = parser.parse_args()
    asyncio.run(create(args.username, args.credential_file))
