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

# ── Load .env.dev into shell environment ──────────────────────────────────────
if [ -f ".env.dev" ]; then
  set -a
  source .env.dev
  set +a
fi

# ── Local database ─────────────────────────────────────────────────────────────
if echo "${DATABASE_URL:-}" | grep -qE "localhost|127\.0\.0\.1"; then
  echo "=== Ensuring local Postgres is running ==="
  bash scripts/local-db.sh start
elif [ -z "${DATABASE_URL:-}" ]; then
  echo "=== DATABASE_URL not set — using SQLite ==="
fi

# ── Run migrations ─────────────────────────────────────────────────────────────
echo "=== Running migrations ==="
python -m alembic upgrade head

# ── Start API ─────────────────────────────────────────────────────────────────
echo "=== Starting Pragna API ==="
echo "    Docs: http://localhost:8000/docs"
echo ""
uvicorn api.app:app --reload --port 8000
