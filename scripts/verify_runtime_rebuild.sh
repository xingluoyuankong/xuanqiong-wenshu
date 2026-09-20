#!/usr/bin/env bash
# Build and verify a clean runtime virtualenv without touching the service environment.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQUIREMENTS="$ROOT/deploy/runtime_requirements.txt"
BASE_PYTHON="${XQ_REBUILD_BASE_PYTHON:-python3}"
VENV="${XQ_REBUILD_VENV:-${TMPDIR:-/tmp}/xq-runtime-rebuild-$$}"
KEEP_VENV="${XQ_REBUILD_KEEP_VENV:-0}"

if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "[runtime-rebuild] missing requirements: $REQUIREMENTS" >&2
  exit 2
fi

cleanup() {
  if [[ "$KEEP_VENV" != "1" ]]; then
    rm -rf -- "$VENV"
  fi
}
trap cleanup EXIT

rm -rf -- "$VENV"
"$BASE_PYTHON" -m venv "$VENV"
PY="$VENV/bin/python"
"$PY" -m pip install --disable-pip-version-check --no-input --quiet -r "$REQUIREMENTS"

env -u PYTHONPATH PYTHONPATH="$ROOT:$ROOT/backend" "$PY" "$ROOT/scripts/verify_runtime_rebuild.py"