#!/usr/bin/env bash
# dev.sh — launch lcsr in development mode.
#
# Uses ~/.lcsr-dev as the data directory (isolated from your real log).
# Enables pywebview DevTools: right-click → Inspect Element in the app window.
#
# First time setup:
#   python tools/seed_dev.py     # populate dev data dir with realistic entries
#   bash dev.sh                  # launch
#
# Subsequent sessions:
#   bash dev.sh                  # just launch, data persists between sessions
#
# Reset dev data:
#   python tools/seed_dev.py --reset && bash dev.sh

set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${REPO_DIR}/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
  echo "✗ .venv not found. Run bash install.sh first." >&2
  exit 1
fi

# Seed dev data if the log doesn't exist yet.
DEV_LOG="${HOME}/.lcsr-dev/log.jsonl"
if [ ! -f "$DEV_LOG" ]; then
  echo "→ No dev data found. Seeding ~/.lcsr-dev..."
  "$PYTHON" "${REPO_DIR}/tools/seed_dev.py"
fi

echo "→ Launching lcsr in dev mode (data: ~/.lcsr-dev, DevTools: on)"
exec "$PYTHON" -m lcsr app --dev --debug
