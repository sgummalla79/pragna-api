#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Create virtual environment if it doesn't exist
if [ ! -f ".venv/bin/activate" ]; then
  echo "=== Creating virtual environment ==="
  python3 -m venv .venv
fi

# Activate virtual environment if not already active
if [ -z "${VIRTUAL_ENV:-}" ]; then
  source .venv/bin/activate
fi

# Install dependencies if needed
if ! python -c "import pytest" 2>/dev/null; then
  echo "=== Installing dependencies ==="
  pip install -r requirements.txt
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
