#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Virtual environment ────────────────────────────────────────────────────────
if [ ! -f ".venv/bin/activate" ]; then
  echo "=== Creating virtual environment ==="
  python3 -m venv .venv
fi

if [ -z "${VIRTUAL_ENV:-}" ]; then
  source .venv/bin/activate
fi

if ! python -c "import uvicorn" 2>/dev/null; then
  echo "=== Installing dependencies ==="
  pip install -r requirements.txt
fi

# ── Local database ─────────────────────────────────────────────────────────────
# Only start Docker Postgres if DATABASE_URL is set to localhost
DB_URL=$(grep -E '^DATABASE_URL=' .env.dev 2>/dev/null | cut -d= -f2- || echo "")
if echo "$DB_URL" | grep -qE "localhost|127\.0\.0\.1"; then
  echo "=== Ensuring local Postgres is running ==="
  bash scripts/local-db.sh start
elif [ -z "$DB_URL" ]; then
  echo "=== DATABASE_URL not set — using SQLite ==="
fi

# ── Run migrations ─────────────────────────────────────────────────────────────
echo "=== Running migrations ==="
APP_ENV=dev python -m alembic upgrade head

# ── Start API ─────────────────────────────────────────────────────────────────
echo "=== Starting Pragna API ==="
echo "    Docs: http://localhost:8000/docs"
echo ""
APP_ENV=dev uvicorn api.app:app --reload --port 8000
