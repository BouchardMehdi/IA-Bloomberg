"""Deployment contract: render safe Nginx and resolve real Compose selection.

Docker config does not start containers or access the existing application.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render_nginx", ROOT / "deploy/render-nginx.py")
nginx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nginx)


def test_nginx_custom_ports_preserve_api_path_and_replace_forwarded_headers():
    config = nginx.render({"SITE_DOMAIN":"market.company.test", "VPS_FRONTEND_PORT":"18088", "VPS_BACKEND_PORT":"13008"})
    assert "server_name market.company.test;" in config
    assert "proxy_pass http://127.0.0.1:13008;" in config
    assert "proxy_pass http://127.0.0.1:18088;" in config
    assert "location /api/" in config
    assert "X-Forwarded-For $remote_addr" in config
    assert "$proxy_add_x_forwarded_for" not in config
    assert "X-Forwarded-Proto $scheme" in config
    assert "__SITE_DOMAIN__" not in config


@pytest.mark.parametrize("domain", ["https://market.company.test", "market.company.test;include /etc/passwd;", "market.company.test\n}", "../a", "-bad.company.test", "market.company.test:443"])
def test_nginx_rejects_invalid_domain_or_directive_injection(domain):
    with pytest.raises(ValueError):
        nginx.render({"SITE_DOMAIN":domain})


@pytest.mark.parametrize("port", ["0", "80", "65536", "8088;", "8088\n", "-1"])
def test_nginx_rejects_invalid_port(port):
    with pytest.raises(ValueError):
        nginx.render({"SITE_DOMAIN":"market.company.test", "VPS_FRONTEND_PORT":port})


def test_nginx_rejects_equal_ports():
    with pytest.raises(ValueError, match="differ"):
        nginx.render({"SITE_DOMAIN":"market.company.test", "VPS_BACKEND_PORT":"8088"})


@pytest.mark.skipif(not shutil.which("docker"), reason="Docker Compose CLI required; no daemon needed")
def test_plain_compose_uses_only_production_and_never_loads_local_override(tmp_path):
    for name in ("docker-compose.yml", "docker-compose.production.yml"):
        shutil.copy2(ROOT / name, tmp_path / name)
    # A trap override proves plain `docker compose` follows COMPOSE_FILE in .env.
    (tmp_path / "docker-compose.override.yml").write_text(
        "services:\n  unexpected:\n    image: busybox\n  backend:\n    environment:\n      AUTH_ENABLED: 'false'\n")
    template = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    template = (template.replace("REPLACE_WITH_RANDOM_HEX_PASSWORD", "a" * 64)
        .replace("REPLACE_WITH_SHA256_FROM_CONFIGURER", "b" * 64)
        .replace("VPS_FRONTEND_PORT=8088", "VPS_FRONTEND_PORT=18088")
        .replace("VPS_BACKEND_PORT=3008", "VPS_BACKEND_PORT=13008"))
    (tmp_path / ".env").write_text(template, encoding="utf-8")
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("COMPOSE_") or key in {"VPS_FRONTEND_PORT", "VPS_BACKEND_PORT", "POSTGRES_PASSWORD", "AI_WORKER_TOKEN_SHA256"}:
            env.pop(key)
    result = subprocess.run(["docker", "compose", "config", "--format", "json"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "Compose configuration failed (output withheld)"
    config = json.loads(result.stdout)
    assert config["name"] == "market-ai-vps"
    services = config["services"]
    assert set(services) == {"backend", "scheduler", "frontend", "postgres", "redis"}
    for service, port in (("frontend", "18088"), ("backend", "13008")):
        mappings = services[service]["ports"]
        assert len(mappings) == 1
        assert mappings[0]["host_ip"] == "127.0.0.1"
        assert str(mappings[0]["published"]) == port
    assert not services["postgres"].get("ports")
    assert not services["redis"].get("ports")
    for service in ("backend", "scheduler"):
        values = services[service]["environment"]
        assert values["AUTH_ENABLED"] == "true" and values["AUTH_COOKIE_SECURE"] == "true"
        assert values["ENVIRONMENT"] == "production" and values["AI_EXECUTION_MODE"] == "remote"
        assert "app.cli.check_production" in services[service]["command"][-1]
    assert services["frontend"]["environment"]["NODE_ENV"] == "production"
    assert "--proxy-headers" in services["backend"]["command"][-1]
    assert config["volumes"]["postgres_data"]["name"] == "market-ai-vps_postgres_data"
    result = subprocess.run(["docker", "compose", "--profile", "backup", "config", "--format", "json"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "backup" in json.loads(result.stdout)["services"]
