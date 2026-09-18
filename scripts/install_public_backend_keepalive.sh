#!/usr/bin/env bash
# Idempotently install the repository 8013 public backend hook into qwenpaw keepalive.
set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
KEEPALIVE_PATH="${KEEPALIVE_PATH:-/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/qwenpaw-mingzhu/bin/keepalive.sh}"
BACKUP_DIR="${BACKUP_DIR:-/run/csi/mount-root/nas/cdbd15b8c05480833b893f85e09ee146/public-backend}"
HOOK_BEGIN="# xuanqiong-wenshu-public-backend:begin"
HOOK_END="# xuanqiong-wenshu-public-backend:end"
if [[ ! -f "$KEEPALIVE_PATH" ]]; then echo "keepalive file missing: $KEEPALIVE_PATH" >&2; exit 2; fi
mkdir -p "$BACKUP_DIR"
backup="$BACKUP_DIR/keepalive.sh.$(date -u +%Y%m%d-%H%M%S).bak"
cp -p "$KEEPALIVE_PATH" "$backup"
REPO_ROOT="$REPO_ROOT" KEEPALIVE_PATH="$KEEPALIVE_PATH" HOOK_BEGIN="$HOOK_BEGIN" HOOK_END="$HOOK_END" python3 - <<'PY'
import os
from pathlib import Path
keepalive=Path(os.environ["KEEPALIVE_PATH"]); repo=Path(os.environ["REPO_ROOT"]); text=keepalive.read_text(encoding="utf-8"); begin=os.environ["HOOK_BEGIN"]; end=os.environ["HOOK_END"]
if begin in text and end in text:
    print("public keepalive hook already installed")
else:
    marker="# heartbeat for container activity"
    block="\n".join([begin,f"WENSHU_REPO={repo}",'if [ -x "$WENSHU_REPO/scripts/ensure_public_backend.sh" ]; then','  "$WENSHU_REPO/scripts/ensure_public_backend.sh" >>"$LOG" 2>&1 || log \'public backend keepalive failed\'','else','  log \'public backend keepalive script missing\'','fi',end,""])
    if marker not in text: raise SystemExit("keepalive marker missing")
    keepalive.write_text(text.replace(marker,block+marker,1),encoding="utf-8")
    print("public keepalive hook installed")
PY
chmod 755 "$KEEPALIVE_PATH"
sh -n "$KEEPALIVE_PATH"
echo "keepalive=$KEEPALIVE_PATH"
echo "backup=$backup"