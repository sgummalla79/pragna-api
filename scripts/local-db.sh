#!/usr/bin/env bash
# local-db.sh — run a local Postgres 16 container for development
# Usage: ./scripts/local-db.sh [start|stop|status|logs|psql]

set -euo pipefail

CONTAINER="pragna-local-db"
IMAGE="postgres:16-alpine"
DB_NAME="pragna"
DB_USER="pragna"
PORT="5432"

# Pull DB_PASSWORD from .env — try DB_PASSWORD= first, then parse DATABASE_URL
ENV_FILE="$(dirname "$0")/../.env"
DB_PASSWORD=""
if [[ -f "$ENV_FILE" ]]; then
  DB_PASSWORD=$(grep -E '^DB_PASSWORD=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
  if [[ -z "$DB_PASSWORD" ]]; then
    DB_PASSWORD=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
  fi
fi
DB_PASSWORD="${DB_PASSWORD:-localdevpassword}"

CMD="${1:-start}"

case "$CMD" in
  start)
    if docker ps -q --filter "name=^${CONTAINER}$" | grep -q . 2>/dev/null; then
      echo "Already running — postgresql://localhost:${PORT}/${DB_NAME}"
      exit 0
    fi
    if docker ps -aq --filter "name=^${CONTAINER}$" | grep -q . 2>/dev/null; then
      echo "Restarting stopped container…"
      docker start "$CONTAINER"
    else
      echo "Starting fresh Postgres container…"
      docker run -d \
        --name "$CONTAINER" \
        -e POSTGRES_DB="$DB_NAME" \
        -e POSTGRES_USER="$DB_USER" \
        -e POSTGRES_PASSWORD="$DB_PASSWORD" \
        -p "${PORT}:5432" \
        -v "${CONTAINER}-data:/var/lib/postgresql/data" \
        "$IMAGE"
    fi
    echo "Waiting for Postgres to be ready…"
    for i in $(seq 1 20); do
      docker exec "$CONTAINER" pg_isready -U "$DB_USER" -q && break
      sleep 1
    done
    echo "Ready — postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${PORT}/${DB_NAME}"
    ;;
  stop)
    docker stop "$CONTAINER" 2>/dev/null && echo "Stopped." || echo "Not running."
    ;;
  status)
    if docker ps -q --filter "name=^${CONTAINER}$" | grep -q . 2>/dev/null; then
      echo "Running — postgresql://${DB_USER}:${DB_PASSWORD}@localhost:${PORT}/${DB_NAME}"
    else
      echo "Stopped."
    fi
    ;;
  logs)
    docker logs -f "$CONTAINER"
    ;;
  psql)
    docker exec -it "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
    ;;
  *)
    echo "Usage: $0 [start|stop|status|logs|psql]"
    exit 1
    ;;
esac
