"""Exercise the remote installer in a sandbox, without SSH or VPS access."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECIPIENT = "age1" + "a" * 58


@pytest.fixture
def sandbox(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker required")
    probe = subprocess.run(["docker", "image", "inspect", "market-ai-vps-backup-tools"], capture_output=True)
    if probe.returncode:
        pytest.skip("Build deploy/backup as market-ai-vps-backup-tools first")
    (tmp_path / "bin").mkdir()
    # A fake Docker command records calls; no host socket or credentials mounted.
    (tmp_path / "bin/docker").write_text(
        '#!/bin/sh\nset -eu\nprintf "%s\\n" "$*" >> /fixture/calls\n'
        'case "$*" in *BACKUP_ONCE=true*)\n'
        '  mkdir -p /fixture/private-data/backups\n'
        '  touch /fixture/private-data/backups/market-fixture.dump.age\n'
        '  touch /fixture/private-data/backups/market-fixture.dump.age.sha256;; esac\n', encoding="utf-8", newline="\n")
    return tmp_path


def install(folder, content, recipient=RECIPIENT):
    env = folder / ".env"
    env.write_text(content, encoding="utf-8")
    result = subprocess.run([
        "docker", "run", "--rm", "--network", "none",
        "--mount", f"type=bind,source={folder},target=/fixture",
        "--mount", f"type=bind,source={ROOT / 'deploy/backup/enable-vps.sh'},target=/enable.sh,readonly",
        "--entrypoint", "/bin/sh", "market-ai-vps-backup-tools", "-c",
        'chmod 755 /fixture/bin/docker; export PATH=/fixture/bin:$PATH; sh /enable.sh /fixture "$1"',
        "fixture", recipient,
    ], capture_output=True, text=True, timeout=30)
    return result, env.read_text(encoding="utf-8")


@pytest.mark.parametrize("previous", ["", "BACKUP_RECIPIENT=\n", f"BACKUP_RECIPIENT={RECIPIENT}\n"])
def test_enable_preserves_other_settings_and_can_repeat(sandbox, previous):
    base = "COMPOSE_FILE=docker-compose.production.yml\nPOSTGRES_PASSWORD=fixture-only\nVPS_FRONTEND_PORT=8091\n"
    result, updated = install(sandbox, base + previous)
    assert result.returncode == 0, result.stderr
    assert updated == base + f"BACKUP_RECIPIENT={RECIPIENT}\n"
    assert "MARKET_BACKUP_READY=market-fixture.dump.age" in result.stdout
    calls = (sandbox / "calls").read_text()
    assert "-p market-ai-vps --env-file .env -f docker-compose.production.yml" in calls
    assert "--require-backup" in calls and "BACKUP_ONCE=true" in calls
    assert "--profile backup up -d --no-deps backup" in calls
    assert " down" not in calls


@pytest.mark.parametrize("previous", [f"BACKUP_RECIPIENT=age1{'b' * 58}\n", "BACKUP_RECIPIENT=\nBACKUP_RECIPIENT=\n"])
def test_enable_refuses_rotation_or_duplicates_without_changes(sandbox, previous):
    original = "COMPOSE_FILE=docker-compose.production.yml\n" + previous
    result, updated = install(sandbox, original)
    assert result.returncode != 0
    assert updated == original
    assert not (sandbox / "calls").exists()


def test_enable_refuses_development_configuration(sandbox):
    original = "COMPOSE_FILE=docker-compose.yml\n"
    result, updated = install(sandbox, original)
    assert result.returncode != 0 and updated == original
    assert not (sandbox / "calls").exists()


@pytest.mark.parametrize("recipient", ["age1short", "age1" + ";" * 58])
def test_enable_rejects_malformed_public_key_without_changes(sandbox, recipient):
    original = "COMPOSE_FILE=docker-compose.production.yml\nBACKUP_RECIPIENT=\n"
    result, updated = install(sandbox, original, recipient)
    assert result.returncode != 0 and updated == original
    assert not (sandbox / "calls").exists()
