#!/usr/bin/env bash
# Keepalive hook for the managed SPA frontend on port 5174.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/scripts/manage_frontend.sh" start