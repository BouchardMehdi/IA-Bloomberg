#!/bin/sh
# Always use the dedicated production project and env file, never the local override.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ ! -f private-data/vps.env ]; then
    echo 'Missing private-data/vps.env. See docs/HYBRID_DEPLOYMENT.md.' >&2
    exit 1
fi
compose() {
    docker compose -p market-ai-vps --env-file private-data/vps.env -f docker-compose.production.yml "$@"
}
case "${1:-status}" in
    up)
        compose config --quiet
        compose build backend scheduler frontend
        compose run --rm --no-deps backend python -m app.cli.check_production
        compose up -d --wait
        ;;
    stop) compose --profile backup stop ;;
    status) compose --profile backup ps ;;
    logs) compose --profile backup logs --tail 80 "${2:-scheduler}" ;;
    admin) compose exec backend python -m app.cli.create_user "${2:-administrateur}" ;;
    ai-status) compose exec backend python -m app.cli.ai_queue ;;
    retry-ai)
        [ -n "${2:-}" ] || { echo 'Usage: sh deploy/vps.sh retry-ai TASK_UUID' >&2; exit 1; }
        compose exec backend python -m app.cli.ai_queue --retry-failed "$2"
        ;;
    backup)
        compose run --rm --no-deps backend python -m app.cli.check_production --require-backup
        compose --profile backup up -d --build backup
        ;;
    *) echo 'Usage: sh deploy/vps.sh up|stop|status|logs [service]|admin [username]|ai-status|retry-ai UUID|backup' >&2; exit 1 ;;
esac
