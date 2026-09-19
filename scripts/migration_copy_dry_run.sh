#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/server_runtime.sh"
xq_prepare_runtime
exec "$XQ_PYTHON" "$ROOT/scripts/migration_copy_dry_run.py" "$@"