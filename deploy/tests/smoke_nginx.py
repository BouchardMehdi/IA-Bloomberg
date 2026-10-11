"""Validate the actual Nginx config and routing in an isolated, portless container."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def main():
    spec = importlib.util.spec_from_file_location("render_nginx", ROOT / "deploy/render-nginx.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    parent = (ROOT / "private-data").resolve()
    qa = parent / ("nginx-qa-" + uuid4().hex)
    qa.mkdir(parents=True)
    config = renderer.render({"SITE_DOMAIN":"market.company.test"})
    (qa / "default.conf").write_text(config, encoding="utf-8")
    try:
        script = """set -eu
nginx -t
nginx
front=$(wget -qO- --header 'Host: market.company.test' 'http://127.0.0.1/analysis?test=1')
test "$front" = 'front|/analysis?test=1|market.company.test'
api=$(wget -qO- --header 'Host: market.company.test' --header 'X-Forwarded-For: 203.0.113.99' --header 'X-Forwarded-Proto: spoofed' 'http://127.0.0.1/api/v1/ai-worker/claim?test=1')
test "$api" = 'api|/api/v1/ai-worker/claim?test=1|market.company.test|127.0.0.1|http'
nginx -s quit
echo 'Nginx smoke passed: syntax, frontend/API paths, query, Host and forwarded headers.'
"""
        subprocess.run(["docker", "run", "--rm", "--network", "none",
            "--mount", f"type=bind,source={qa / 'default.conf'},target=/etc/nginx/conf.d/default.conf,readonly",
            "--mount", f"type=bind,source={ROOT / 'deploy/tests/nginx-smoke.conf'},target=/etc/nginx/nginx.conf,readonly",
            "--entrypoint", "/bin/sh", "nginx:1.28-alpine", "-c", script], check=True, timeout=180)
    finally:
        # A fixed private test prefix and resolved workspace parent gate deletion.
        if qa.resolve().parent != parent or not qa.name.startswith("nginx-qa-"):
            raise RuntimeError("Unsafe test cleanup path")
        shutil.rmtree(qa)


if __name__ == "__main__":
    main()
