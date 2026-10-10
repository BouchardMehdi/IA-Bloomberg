"""Validate deployment values without printing credentials or connecting to storage."""
import argparse
import os
import re
from urllib.parse import urlsplit

from app.core.config import get_settings


def check(require_backup=False):
    settings = get_settings()
    if settings.environment != "production" or settings.ai_execution_mode != "remote":
        raise ValueError("Use the dedicated production Compose file")
    password = urlsplit(settings.database_url).password or ""
    if not re.fullmatch(r"[a-f0-9]{64}", password):
        raise ValueError("Use a random 64-character hexadecimal database password")
    origins = settings.cors_origins
    if len(origins) != 1 or not origins[0].startswith("https://") or "example." in origins[0]:
        raise ValueError("Configure the real HTTPS domain")
    for name in ("ACME_EMAIL", "SEC_USER_AGENT"):
        value = os.environ.get(name, settings.sec_user_agent if name == "SEC_USER_AGENT" else "")
        if "@" not in value or "example.com" in value or "example.org" in value:
            raise ValueError(f"Configure a real contact for {name}")
    if require_backup and not os.environ.get("BACKUP_RECIPIENT", "").startswith("age1"):
        raise ValueError("Configure the public age BACKUP_RECIPIENT before enabling backup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-backup", action="store_true")
    args = parser.parse_args()
    try:
        check(args.require_backup)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print("Production configuration validated; no secret displayed")
