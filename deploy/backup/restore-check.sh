#!/bin/sh
set -eu
umask 077
: "${RESTORE_DATABASE:?Choose a new database ending in _restore_check}"
case "$RESTORE_DATABASE" in *[!a-z0-9_]*|'') exit 2;; esac
case "$RESTORE_DATABASE" in *_restore_check) ;; *) echo 'Test database suffix required' >&2; exit 2;; esac
[ "$RESTORE_DATABASE" != "$PGDATABASE" ]
[ "$#" -eq 1 ]
archive="$1"
case "$archive" in /backups/market-*.dump.age) ;; *) exit 2;; esac
[ -f "$archive" ] && [ ! -L "$archive" ]
case "$archive" in *..*) exit 2;; esac
sha256sum -c "$archive.sha256"
temp=$(mktemp -d /tmp/market-restore.XXXXXX)
trap 'rm -rf "$temp"' EXIT HUP INT TERM
age -d -i /run/secrets/backup_identity -o "$temp/database.dump" "$archive"
pg_restore --list "$temp/database.dump" > /dev/null
# No --clean, no dropdb: refuses an existing target, including previous tests.
createdb "$RESTORE_DATABASE"
pg_restore --dbname="$RESTORE_DATABASE" --no-owner --no-privileges --exit-on-error "$temp/database.dump"
PGDATABASE="$RESTORE_DATABASE" psql -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version' -c 'SELECT count(*) AS articles FROM articles' -c 'SELECT count(*) AS portfolios FROM paper_portfolios'
echo "Restore check completed; test database retained: $RESTORE_DATABASE"
