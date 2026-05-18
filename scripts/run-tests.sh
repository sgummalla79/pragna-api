#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate virtual environment if not already active
if [ -z "${VIRTUAL_ENV:-}" ]; then
  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
  else
    echo "No .venv found. Run: python3 -m venv .venv && pip install -r requirements.txt"
    exit 1
  fi
fi

echo "=== Running Pragna tests ==="
echo "Python: $(python --version)"
echo "Pytest: $(pytest --version)"
echo ""

pytest tests/unit/ tests/e2e/ \
  -v -s \
  --tb=long \
  -m "not live" \
  --log-cli-level=INFO \
  "$@"
