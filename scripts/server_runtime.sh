#!/usr/bin/env bash
# 玄穹文枢统一 Linux 运行时入口。
# 解析仓库 Python 与外置用户包，避免 start/restart/monitor 三套入口漂移。
set -euo pipefail

XQ_SERVER_REPO_ROOT="${XQ_SERVER_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
XQ_BACKEND_APP="${XQ_BACKEND_APP:-backend.app.main:app}"
XQ_PYTHON="${XQ_PYTHON:-}"

xq_prepare_runtime() {
    local candidates=()
    if [[ -n "${XQ_PYTHON:-}" ]]; then
        candidates+=("$XQ_PYTHON")
    fi
    candidates+=("$XQ_SERVER_REPO_ROOT/.venv/bin/python" "${XQ_SYSTEM_PYTHON:-python3}")

    local python_path="$XQ_SERVER_REPO_ROOT:$XQ_SERVER_REPO_ROOT/backend"
    local package_dir
    for package_dir in \
        "$XQ_SERVER_REPO_ROOT/.venv/lib/python3.11/site-packages" \
        "${XQ_USER_PACKAGES_DIR:-/app/user-packages/python}" \
        "${XQ_APP_SITE_PACKAGES:-/app/venv/lib/python3.11/site-packages}"; do
        if [[ -d "$package_dir" ]]; then
            python_path="$python_path:$package_dir"
        fi
    done

    local candidate
    for candidate in "${candidates[@]}"; do
        if [[ "$candidate" != */* ]]; then
            candidate="$(command -v "$candidate" 2>/dev/null || true)"
        fi
        [[ -x "$candidate" ]] || continue
        if PYTHONPATH="$python_path" "$candidate" -c 'import uvicorn, fastapi, sqlalchemy, aiosqlite' >/dev/null 2>&1; then
            XQ_PYTHON="$candidate"
            export XQ_PYTHON XQ_SERVER_REPO_ROOT XQ_BACKEND_APP PYTHONPATH="$python_path"
            return 0
        fi
    done

    echo "[xuanqiong-runtime] no Python candidate can import uvicorn/fastapi/sqlalchemy/aiosqlite" >&2
    echo "[xuanqiong-runtime] repo=$XQ_SERVER_REPO_ROOT candidates=${candidates[*]}" >&2
    return 1
}

xq_print_runtime() {
    xq_prepare_runtime
    echo "XQ_SERVER_REPO_ROOT=$XQ_SERVER_REPO_ROOT"
    echo "XQ_PYTHON=$XQ_PYTHON"
    echo "XQ_BACKEND_APP=$XQ_BACKEND_APP"
    echo "XQ_PYTHONPATH=$PYTHONPATH"
    "$XQ_PYTHON" - <<'PY'
import sys
import aiosqlite, fastapi, sqlalchemy, uvicorn
print(f"RUNTIME_IMPORTS=ok python={sys.executable}")
print(f"RUNTIME_VERSIONS=fastapi={fastapi.__version__} sqlalchemy={sqlalchemy.__version__} uvicorn={uvicorn.__version__}")
PY
}
