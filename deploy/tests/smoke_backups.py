"""Real encrypted round trip on disposable PostgreSQL; never connects to the VPS.

Requires Docker images market-ai-backend and pgvector/pgvector:pg16; Windows also
exercises the end-user PowerShell helper in an isolated copy of its directories.
All keys and reports generated here are TEST fixtures, separate from user keys.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "market-ai-vps-backup-tools"


def run(*args, expected=0, **kwargs):
    result = subprocess.run(list(args), capture_output=True, text=True, timeout=180, **kwargs)
    if expected == 0 and result.returncode:
        raise RuntimeError(f"Command failed: {args[0]}\n{result.stdout}\n{result.stderr}")
    if expected != 0 and not result.returncode:
        raise AssertionError("Unsafe operation unexpectedly succeeded")
    return result


def main():
    tag = uuid4().hex
    work = ROOT / "private-data" / "backup-tests" / tag
    archive_dir = work / "private-data/vps-backup/archives"
    archive_dir.mkdir(parents=True)
    key_dir = archive_dir.parent
    network = f"market-backup-fixture-{tag}"
    db = f"{network}-db"
    created = False
    try:
        run("docker", "build", "-t", IMAGE, str(ROOT / "deploy/backup"))
        run("docker", "network", "create", "--internal", network)
        created = True
        run("docker", "create", "--name", db, "--network", network,
            "-e", "POSTGRES_DB=market_ai", "-e", "POSTGRES_USER=market_ai",
            "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "pgvector/pgvector:pg16")
        run("docker", "start", db)
        for _ in range(45):
            ready = subprocess.run(["docker", "exec", db, "pg_isready", "-U", "market_ai"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Fixture database did not become ready")
        # Apply the actual application's migrations, without mounting its .env.
        run("docker", "run", "--rm", "--network", network,
            "--mount", f"type=bind,source={ROOT / 'backend/app'},target=/app/app,readonly",
            "--mount", f"type=bind,source={ROOT / 'backend/migrations'},target=/app/migrations,readonly",
            "-e", f"DATABASE_URL=postgresql+asyncpg://market_ai@{db}/market_ai",
            "market-ai-backend", "alembic", "upgrade", "head")
        sql = "INSERT INTO workspace_users (id,username,password_hash,role,enabled) VALUES ('11111111-1111-1111-1111-111111111111','backup-fixture','disabled-fixture','editor',false);"
        run("docker", "exec", db, "psql", "-U", "market_ai", "-d", "market_ai", "-v", "ON_ERROR_STOP=1", "-c", sql)
        run("docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,source={key_dir},target=/keys",
            "--entrypoint", "age-keygen", IMAGE, "-o", "/keys/backup-identity.key")
        recipient = run("docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,source={key_dir},target=/keys,readonly",
            "--entrypoint", "age-keygen", IMAGE, "-y", "/keys/backup-identity.key").stdout.strip()
        def backup():
            return run("docker", "run", "--rm", "--network", network, "--tmpfs", "/tmp:size=1g",
                "--mount", f"type=bind,source={archive_dir},target=/backups",
                "-e", f"PGHOST={db}", "-e", "PGUSER=market_ai", "-e", "PGDATABASE=market_ai",
                "-e", "PGPASSWORD=unused-fixture", "-e", f"BACKUP_RECIPIENT={recipient}", "-e", "BACKUP_ONCE=true", IMAGE)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: backup(), range(2)))
        archives = sorted(archive_dir.glob("market-*.dump.age"))
        assert len(archives) == 2, "Concurrent backups must not overwrite each other"
        archive = archives[0]
        assert archive.read_bytes().startswith(b"age-encryption.org/v1")
        def restore(name, file=archive, expected=0, identity="backup-identity.key"):
            return run("docker", "run", "--rm", "--network", network, "--tmpfs", "/tmp:size=1g",
                "--mount", f"type=bind,source={archive_dir},target=/backups,readonly",
                "--mount", f"type=bind,source={key_dir / identity},target=/run/secrets/backup_identity,readonly",
                "-e", f"PGHOST={db}", "-e", "PGUSER=market_ai", "-e", "PGDATABASE=market_ai",
                "-e", f"RESTORE_DATABASE={name}", "--entrypoint", "/bin/sh", IMAGE,
                "/opt/backup/restore-check.sh", f"/backups/{file.name}", expected=expected)
        restore("fixture_restore_check")
        value = run("docker", "exec", db, "psql", "-U", "market_ai", "-d", "fixture_restore_check", "-Atc",
            "SELECT username || ':' || role || ':' || enabled FROM workspace_users").stdout.strip()
        assert value == "backup-fixture:editor:false", "Account data must survive restoration"
        restore("fixture_restore_check", expected=1)  # existing target refused
        restore("market_ai", expected=1)  # live source refused
        run("docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,source={key_dir},target=/keys",
            "--entrypoint", "age-keygen", IMAGE, "-o", "/keys/wrong-identity.key")
        restore("wrong_key_restore_check", expected=1, identity="wrong-identity.key")
        damaged = archive_dir / "market-corrupt.dump.age"
        damaged.write_bytes(archive.read_bytes() + b"corrupt")
        checksum = archive.with_suffix(archive.suffix + ".sha256").read_text()
        damaged.with_suffix(damaged.suffix + ".sha256").write_text(checksum.replace(archive.name, damaged.name))
        restore("corrupt_restore_check", file=damaged, expected=1)
        absent = run("docker", "exec", db, "psql", "-U", "market_ai", "-d", "market_ai", "-Atc",
            "SELECT count(*) FROM pg_database WHERE datname IN ('wrong_key_restore_check','corrupt_restore_check')").stdout.strip()
        assert absent == "0", "Failures must not create target databases"
        if os.name == "nt":
            deploy = work / "deploy"
            deploy.mkdir()
            shutil.copy2(ROOT / "deploy/Manage-VpsBackups.ps1", deploy)
            shutil.copytree(ROOT / "deploy/backup", deploy / "backup")
            run("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(deploy / "Manage-VpsBackups.ps1"), "-Action", "Verify", "-Archive", str(archive))
            report = json.loads((key_dir / "last-verification.json").read_text())
            assert report["status"] == "restored" and report["production_restore"] is False
            assert report["target"] == "isolated_local_postgresql"
            assert report["archive"] == archive.name
        print("PASS: concurrent encrypted backups, restored account/role, wrong key, corrupt archive, existing/live target refusal and isolated helper.")
        print(f"TEST fixtures retained separately: {work.relative_to(ROOT)}")
    finally:
        if created:
            # Names contain this run's UUID; no existing application resources.
            subprocess.run(["docker", "rm", "-f", "-v", db], capture_output=True)
            subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
