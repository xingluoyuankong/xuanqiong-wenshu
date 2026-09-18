#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XQ_BACKEND_ROLE=public_backend XQ_BACKEND_HOST=0.0.0.0 XQ_BACKEND_PORT=8013 XQ_BACKEND_STATE_DIR="$ROOT/logs/public-backend-8013" exec "$ROOT/scripts/manage_internal_backend.sh" "$@"
