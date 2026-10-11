#!/bin/sh
# Always select production explicitly; never merge the development override.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -f .env ] && grep -q '^COMPOSE_FILE=docker-compose.production.yml[[:space:]]*$' .env; then
    vps_env_file=.env
elif [ -f private-data/vps.env ]; then
    # Compatibility with the original hybrid setup; no secrets are moved.
    vps_env_file=private-data/vps.env
else
    echo 'Prepare the VPS .env from .env.production.example. See deploy.md.' >&2
    exit 1
fi
compose() {
    docker compose -p market-ai-vps --env-file "$vps_env_file" -f docker-compose.production.yml "$@"
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
    nginx)
        compose run --rm --no-deps -T -v "$PWD/deploy:/deployment:ro" backend python /deployment/render-nginx.py
        ;;
    retry-ai)
        [ -n "${2:-}" ] || { echo 'Usage: sh deploy/vps.sh retry-ai TASK_UUID' >&2; exit 1; }
        compose exec backend python -m app.cli.ai_queue --retry-failed "$2"
        ;;
    backup)
        compose run --rm --no-deps backend python -m app.cli.check_production --require-backup
        compose --profile backup up -d --build backup
        ;;
    *) echo 'Usage: sh deploy/vps.sh up|stop|status|logs [service]|admin [username]|ai-status|retry-ai UUID|backup|nginx' >&2; exit 1 ;;
esac
