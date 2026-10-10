"""Create and migrate a fresh isolated database without changing the live schema."""
import asyncio
import os
import subprocess

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

QA_DATABASE = "market_ai_workspace_qa"


async def main():
    url = make_url(get_settings().database_url)
    assert url.database != QA_DATABASE
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as connection:
        exists = (await connection.execute(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": QA_DATABASE})).scalar()
        if exists:
            raise SystemExit("QA database already exists; no database overwritten.")
        await connection.execute(text(f'CREATE DATABASE "{QA_DATABASE}"'))
    await admin.dispose()
    env = {**os.environ, "DATABASE_URL": url.set(database=QA_DATABASE).render_as_string(hide_password=False),
           "AUTH_ENABLED": "false", "ENVIRONMENT": "development"}
    # No credential is placed on the command line or printed.
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    subprocess.run(["python", "-m", "tests.smoke_workspace"], env=env, check=True)
    print("Isolated migration/API verification succeeded. QA database retained for encrypted backup/restore verification; live schema unchanged.")


if __name__ == "__main__":
    asyncio.run(main())
