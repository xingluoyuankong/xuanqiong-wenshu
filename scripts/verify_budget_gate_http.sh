#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/server_runtime.sh"
xq_prepare_runtime
if [[ -f "$ROOT/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/backend/.env"
  set +a
fi
exec "$XQ_PYTHON" "$ROOT/scripts/verify_budget_gate_http.py"
