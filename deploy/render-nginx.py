"""Render only domain/ports, never secrets or shell code, using VPS service env."""
import os
from pathlib import Path
import re


def render(environment):
    domain = environment.get("SITE_DOMAIN", "")
    labels = domain.split(".")
    if (len(domain) > 253 or len(labels) < 2 or
            any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)):
        raise ValueError("SITE_DOMAIN must be a DNS hostname without scheme, port or path")
    ports = []
    for key, default in (("VPS_FRONTEND_PORT", "8088"), ("VPS_BACKEND_PORT", "3008")):
        value = environment.get(key, default)
        if not re.fullmatch(r"[0-9]{1,5}", value) or not 1024 <= int(value) <= 65535:
            raise ValueError(f"{key} must be a port between 1024 and 65535")
        ports.append(str(int(value)))
    if ports[0] == ports[1]:
        raise ValueError("Frontend and backend ports must differ")
    template = Path(__file__).with_name("nginx.conf.template").read_text(encoding="utf-8")
    return (template.replace("__SITE_DOMAIN__", domain)
            .replace("__FRONTEND_PORT__", ports[0]).replace("__BACKEND_PORT__", ports[1]))


if __name__ == "__main__":
    try:
        print(render(os.environ), end="")
    except ValueError as error:
        raise SystemExit(str(error)) from None
