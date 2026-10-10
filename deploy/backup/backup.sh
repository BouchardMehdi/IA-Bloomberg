#!/bin/sh
set -eu
umask 077
: "${BACKUP_RECIPIENT:?A public age recipient is required}"
: "${PGHOST:?PGHOST required}"
: "${PGDATABASE:?PGDATABASE required}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"
case "${BACKUP_INTERVAL_SECONDS:-86400}" in *[!0-9]*|'') exit 2;; esac
case "${BACKUP_RETENTION_DAYS:-14}" in *[!0-9]*|'') exit 2;; esac
[ "${BACKUP_INTERVAL_SECONDS:-86400}" -ge 3600 ]
[ "${BACKUP_RETENTION_DAYS:-14}" -ge 1 ]
mkdir -p /backups
while :; do
    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    # Dump plaintext only into an in-memory tmpfs. Never stream a partially
    # failed pg_dump into an apparently successful encrypted backup.
    temp=$(mktemp -d /tmp/market-backup.XXXXXX)
    trap 'rm -rf "$temp"' EXIT HUP INT TERM
    if pg_dump --format=custom --no-owner --no-privileges --file="$temp/database.dump" &&
       age -r "$BACKUP_RECIPIENT" -o "$temp/database.age" "$temp/database.dump"; then
        target="/backups/market-$stamp-$$.dump.age"
        cp "$temp/database.age" "$target.partial"
        mv "$target.partial" "$target"
        sha256sum "$target" > "$target.sha256"
        # Only our own encrypted archives in the fixed backup directory.
        find /backups -maxdepth 1 -type f -name 'market-*.dump.age*' -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
        echo "Encrypted PostgreSQL backup completed: $stamp"
    else
        echo "Backup failed; previous archives retained" >&2
        rm -rf "$temp"
        exit 1
    fi
    rm -rf "$temp"
    [ "${BACKUP_ONCE:-false}" = true ] && exit 0
    sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
