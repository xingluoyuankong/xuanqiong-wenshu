#!/usr/bin/env bash
# Bohrium-2 native release runner for the non-Docker deployment.
# It deliberately never uses git reset --hard and never deletes SQLite data.

set -Eeuo pipefail

REPO_DIR="${XQ_REPO_DIR:-/opt/xuanqiong-wenshu}"
BRANCH="${XQ_BRANCH:-codex/bohrium-integration-20260831}"
REMOTE="${XQ_REMOTE:-origin}"
BUNDLE_PATH=""
SKIP_FRONTEND_BUILD=0

usage() {
  cat <<'USAGE'
Usage: bash deploy/scripts/bohrium_native_release.sh [options]

Options:
  --repo DIR             Release worktree, default /opt/xuanqiong-wenshu
  --branch REF           Remote branch, default codex/bohrium-integration-20260831
  --bundle FILE          Fetch commits from a local Git bundle instead of network fetch
  --skip-frontend-build  Do not run npm ci/build-only (only for an already built verified release)
  -h, --help             Print this help

The script creates a timestamped SQLite/upload backup, fast-forwards only,
rebuilds the frontend, restarts the project's isolated Supervisor process group,
and validates /api/health. It does not touch OpenClaw or system Supervisor.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_DIR="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --bundle) BUNDLE_PATH="$2"; shift 2 ;;
    --skip-frontend-build) SKIP_FRONTEND_BUILD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

require_file() {
  [[ -f "$1" ]] || { echo "Missing required file: $1" >&2; exit 1; }
}

[[ -e "$REPO_DIR/.git" ]] || { echo "Missing Git worktree: $REPO_DIR" >&2; exit 1; }
require_file "$REPO_DIR/runtime.env"
require_file "$REPO_DIR/run/supervisord.conf"
require_file "$REPO_DIR/backend/.venv/bin/python"
require_file "$REPO_DIR/backend/storage/xuanqiong_wenshu.db"

cd "$REPO_DIR"
BACKUP_ROOT="${XQ_BACKUP_ROOT:-/opt/xuanqiong-wenshu-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP_DIR"

current_head="$(git rev-parse HEAD)"
printf 'release_start=%s\nrepo=%s\nhead_before=%s\n' "$STAMP" "$REPO_DIR" "$current_head"

# This is a logical SQLite backup, safe while the API remains online.
"$REPO_DIR/backend/.venv/bin/python" - "$REPO_DIR/backend/storage/xuanqiong_wenshu.db" "$BACKUP_DIR/xuanqiong_wenshu.db" <<'PY'
import sqlite3
import sys
from pathlib import Path
src, dst = map(Path, sys.argv[1:])
with sqlite3.connect(src) as source, sqlite3.connect(dst) as target:
    source.backup(target)
print(dst)
PY

for upload_dir in novel_imports style_uploads; do
  if [[ -d "$REPO_DIR/backend/storage/$upload_dir" ]]; then
    tar -C "$REPO_DIR/backend/storage" -czf "$BACKUP_DIR/$upload_dir.tgz" "$upload_dir"
  fi
done

if [[ -n "$BUNDLE_PATH" ]]; then
  require_file "$BUNDLE_PATH"
  git fetch "$BUNDLE_PATH" "$BRANCH"
  target_ref="FETCH_HEAD"
else
  git fetch "$REMOTE" "$BRANCH"
  target_ref="$REMOTE/$BRANCH"
fi

git merge --ff-only "$target_ref"
new_head="$(git rev-parse HEAD)"

"$REPO_DIR/backend/.venv/bin/python" -m pip install -r "$REPO_DIR/backend/requirements.txt"

if [[ "$SKIP_FRONTEND_BUILD" -eq 0 ]]; then
  pushd "$REPO_DIR/frontend" >/dev/null
  npm ci --prefer-offline --no-audit
  npm run build-only
  popd >/dev/null
fi

supervisorctl -c "$REPO_DIR/run/supervisord.conf" restart \
  xuanqiong-wenshu-api xuanqiong-wenshu-nginx
sleep 8
supervisorctl -c "$REPO_DIR/run/supervisord.conf" status
health="$(curl --noproxy '*' -fsS http://127.0.0.1:18080/api/health)"
db_hash="$(sha256sum "$REPO_DIR/backend/storage/xuanqiong_wenshu.db" | awk '{print $1}')"
tunnel_url="$(grep -hEo 'https://[-a-z0-9]+\.trycloudflare\.com' "$REPO_DIR/logs/cloudflared.log" "$REPO_DIR/logs/cloudflared-error.log" 2>/dev/null | tail -1 || true)"

python3 - "$REPO_DIR/run/release.json" "$new_head" "$db_hash" "$tunnel_url" "$BACKUP_DIR" <<'PY'
import json
import sys
from pathlib import Path
path, commit, digest, tunnel, backup_dir = sys.argv[1:]
current = {}
if Path(path).exists():
    current = json.loads(Path(path).read_text(encoding="utf-8"))
current.update(
    commit=commit,
    database_sha256=digest,
    public_tunnel=tunnel or current.get("public_tunnel", ""),
    last_backup_directory=backup_dir,
)
Path(path).write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
chmod 600 "$REPO_DIR/run/release.json"

printf 'release_complete=%s\nhead_after=%s\nbackup=%s\ndatabase_sha256=%s\nhealth=%s\npublic_tunnel=%s\n' \
  "$STAMP" "$new_head" "$BACKUP_DIR" "$db_hash" "$health" "$tunnel_url"
