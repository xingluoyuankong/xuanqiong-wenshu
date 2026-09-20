#!/usr/bin/env bash
# Read-only production topology audit for qwenpaw-mingzhu.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEPALIVE_PATH="${KEEPALIVE_PATH:-/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/qwenpaw-mingzhu/bin/keepalive.sh}"
failures=0
pass(){ printf '[PASS] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; failures=$((failures+1)); }
check_cmd(){ command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"; }

for cmd in bash curl git lsof python3; do check_cmd "$cmd"; done

for manifest in "$ROOT/logs/public-backend-8013/manifest.json" "$ROOT/logs/internal-backend-8099/manifest.json" "$ROOT/logs/frontend-5174/manifest.json"; do
  if [[ ! -f "$manifest" ]]; then fail "manifest missing: $manifest"; continue; fi
  if python3 - "$manifest" <<'PY'
import json, sys
d=json.load(open(sys.argv[1]))
assert d.get("status") == "running"
assert d.get("code_drift") is False
assert d.get("working_tree_dirty") is False
assert d.get("process_commit") == d.get("current_commit")
PY
  then pass "manifest aligned: $manifest"; else fail "manifest drift: $manifest"; fi
done

if [[ -f "$KEEPALIVE_PATH" ]]; then
  if [[ "$(stat -c %a "$KEEPALIVE_PATH")" == "755" ]]; then pass "keepalive executable"; else fail "keepalive permission is not 755"; fi
  sh -n "$KEEPALIVE_PATH" && pass "keepalive syntax" || fail "keepalive syntax"
  [[ "$(grep -c 'ensure_internal_backend.sh' "$KEEPALIVE_PATH")" == "2" ]] && pass "one internal hook" || fail "internal hook count"
  [[ "$(grep -c 'ensure_public_backend.sh' "$KEEPALIVE_PATH")" == "2" ]] && pass "one public hook" || fail "public hook count"
else
  fail "keepalive missing: $KEEPALIVE_PATH"
fi

for endpoint in "http://127.0.0.1:8013/api/health" "http://127.0.0.1:8099/api/health"; do
  if curl -fsS --max-time 8 "$endpoint" >/dev/null; then pass "health: $endpoint"; else fail "health: $endpoint"; fi
done

for route in / /workspace /admin /settings; do
  if body="$(curl -fsS --max-time 8 "http://127.0.0.1:5174$route")" && [[ "$body" == *'id="app"'* ]]; then
    pass "frontend route: $route"
  else
    fail "frontend route: $route"
  fi
done
for endpoint in "http://127.0.0.1:5174/missing.js" "http://127.0.0.1:5174/api/health"; do
  if [[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "$endpoint" || true)" == "404" ]]; then
    pass "frontend boundary: $endpoint"
  else
    fail "frontend boundary: $endpoint"
  fi
done

if "$ROOT/scripts/audit_sqlite_integrity.py" >/tmp/xq-topology-integrity.out; then pass "sqlite integrity"; else fail "sqlite integrity"; fi
if "$ROOT/scripts/audit_sqlite_schema.sh" >/tmp/xq-topology-schema.out; then pass "sqlite schema drift"; else fail "sqlite schema drift"; fi
if "$ROOT/scripts/verify_sqlite_baseline.py" >/tmp/xq-topology-baseline.out; then pass "sqlite schema baseline"; else fail "sqlite schema baseline"; fi
if "$ROOT/scripts/verify_migration_manifest.py" >/tmp/xq-topology-migration.out; then pass "migration provenance"; else fail "migration provenance"; fi
if git -C "$ROOT" diff --check; then pass "git diff check"; else fail "git diff check"; fi
remote_counts="$(git -C "$ROOT" rev-list --left-right --count origin/codex/server-us010-r1...HEAD 2>/dev/null || echo "1 1")"
remote_counts="$(printf '%s' "$remote_counts" | tr '\t' ' ' | xargs)"
if [[ "$remote_counts" == "0 0" ]]; then pass "git remote sync"; else fail "git remote sync ($remote_counts)"; fi

printf 'AUDIT_RESULT=%s\n' "$([[ $failures -eq 0 ]] && echo PASS || echo FAIL)"
exit "$failures"
