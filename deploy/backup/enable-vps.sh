#!/bin/sh
# Fed to SSH on stdin. Only the public recipient is sent; no private key.
set -eu
umask 077
[ "$#" -eq 2 ]
project="$1"
recipient="$2"
case "$project" in /*) ;; *) exit 2;; esac
case "$project" in *[!a-zA-Z0-9_/.-]*|*..*) exit 2;; esac
case "$recipient" in age1*) ;; *) exit 2;; esac
case "$recipient" in *[!a-z0-9]*) exit 2;; esac
[ "${#recipient}" -eq 62 ] || exit 2
cd "$project"
[ -f .env ] && [ ! -L .env ]
grep -q '^COMPOSE_FILE=docker-compose.production.yml[[:space:]]*$' .env

# Refuse implicit key rotation: old archives must remain decryptable.
count=$(grep -c '^BACKUP_RECIPIENT=' .env || true)
[ "$count" -le 1 ] || { echo 'Duplicate BACKUP_RECIPIENT entries; edit manually.' >&2; exit 1; }
old=$(sed -n 's/^BACKUP_RECIPIENT=//p' .env | tr -d '\r')
[ -z "$old" ] || [ "$old" = "$recipient" ] || {
    echo 'Existing backup key differs; keep it and use its matching private key.' >&2
    exit 1
}
temp=$(mktemp .env.backup.XXXXXX)
trap 'rm -f "$temp"' EXIT HUP INT TERM
awk -v recipient="$recipient" '
    /^BACKUP_RECIPIENT=/ { print "BACKUP_RECIPIENT=" recipient; found=1; next }
    { print }
    END { if (!found) print "BACKUP_RECIPIENT=" recipient }
' .env > "$temp"
chmod 600 "$temp"
mv "$temp" .env

# Explicit file and project isolate this from other VPS projects and overrides.
compose() { docker compose -p market-ai-vps --env-file .env -f docker-compose.production.yml "$@"; }
compose config --quiet
compose run --rm --no-deps backend python -m app.cli.check_production --require-backup
compose build backup
compose run --rm --no-deps -e BACKUP_ONCE=true backup
compose --profile backup up -d --no-deps backup

# Only complete archives with a published checksum are eligible for transfer.
archive=$(find private-data/backups -maxdepth 1 -type f -name 'market-*.dump.age.sha256' | sort -r | head -n 1)
[ -n "$archive" ]
archive=${archive%.sha256}
[ -f "$archive" ] && [ ! -L "$archive" ]
echo "MARKET_BACKUP_READY=${archive##*/}"
