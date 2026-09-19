#!/usr/bin/env bash
# Run backend tests through the same dependency resolution used by the server.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/server_runtime.sh"
xq_prepare_runtime
printf 'TEST_RUNTIME_PYTHON=%s\n' "$XQ_PYTHON"
printf 'TEST_RUNTIME_PYTHONPATH=%s\n' "$PYTHONPATH"
cd "$ROOT/backend"
exec "$XQ_PYTHON" -m pytest -q "$@"