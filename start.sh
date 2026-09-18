#!/bin/bash
# 玄穹文枢 start script - Linux/Mac version with graceful failure cleanup
set -euo pipefail

TIMEOUT_SECONDS=${XUANQIONG_WENSHU_STARTUP_TIMEOUT:-30}
CHECK_INTERVAL_MS=${XUANQIONG_WENSHU_CHECK_INTERVAL:-500}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${SCRIPT_DIR}"
LOGS_ROOT="${REPO}/logs"

echo "=== 玄穹文枢启动 (Linux/Mac) ==="
echo "repo: ${REPO}"
echo "timeout: ${TIMEOUT_SECONDS}s"

RUN_ID=$(date +%Y%m%d-%H%M%S)
RUN_DIR="${LOGS_ROOT}/run-${RUN_ID}"
mkdir -p "${RUN_DIR}"

export XUANQIONG_WENSHU_LOG_DIR="${RUN_DIR}"
export LOGGING_LEVEL="INFO"
export CONSOLE_LOGGING_LEVEL="INFO"
export PYTHONUNBUFFERED=1
export PYTHONUTF8=1

BACKEND_HOST="${XUANQIONG_WENSHU_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${XUANQIONG_WENSHU_BACKEND_PORT:-8013}"
FRONTEND_HOST="${XUANQIONG_WENSHU_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${XUANQIONG_WENSHU_FRONTEND_PORT:-5174}"

backend_base_url="http://${BACKEND_HOST}:${BACKEND_PORT}"
frontend_base_url="http://${FRONTEND_HOST}:${FRONTEND_PORT}"

cleanup_manager_script="${REPO}/backend/app/utils/process_cleanup.py"

trap 'handle_failure' ERR SIGINT SIGTERM

handle_failure() {
    local exit_code=$?
    echo "⚠ STARTUP FAILED or interrupted" >&2
    
    # Cleanup tracked processes
    echo "Cleaning up orphaned processes..." >&2
    if command -v pkill >/dev/null; then
        pkill -f "uvicorn.*${BACKEND_PORT}" 2>/dev/null || true
        pkill -f "http.server.*${FRONTEND_PORT}" 2>/dev/null || true
    fi
    
    sleep 1
    
    # Force kill if still running
    if pid_of_uvicorn=$(pgrep -f "uvicorn.*${BACKEND_PORT}" 2>/dev/null); then
        echo "Force-killing uvicorn (PID: ${pid_of_uvicorn})" >&2
        kill -9 "${pid_of_uvicorn}" 2>/dev/null || true
    fi
    
    if pid_of_frontend=$(pgrep -f "http.server.*${FRONTEND_PORT}" 2>/dev/null); then
        echo "Force-killing frontend (PID: ${pid_of_frontend})" >&2
        kill -9 "${pid_of_frontend}" 2>/dev/null || true
    fi
    
    # Clean socket files
    echo "Cleaning socket files..." >&2
    rm -f "${RUN_DIR}/uvicorn.sock" 2>/dev/null || true
    rm -f "${RUN_DIR}/fastapi.sock" 2>/dev/null || true
    rm -f /tmp/uvcorn*.sock 2>/dev/null || true
    
    echo "Cleanup complete" >&2
    exit "${exit_code}"
}

check_process_alive() {
    local pid=$1
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

wait_for_backend_health() {
    local start_time=$(date +%s)
    local elapsed=0
    
    while [ $elapsed -lt ${TIMEOUT_SECONDS} ]; do
        if curl -s -o /dev/null -w "%{http_code}" "${backend_base_url}/api/health" | grep -q "200"; then
            echo "✓ Backend healthy after ${elapsed}s"
            return 0
        fi
        
        sleep $(echo "scale=2; ${CHECK_INTERVAL_MS} / 1000" | bc)
        elapsed=$(($(date +%s) - start_time))
        
        if [ $((elapsed % 5)) -eq 0 ]; then
            local remaining=$((TIMEOUT_SECONDS - elapsed))
            echo "  ⏱ Backend starting... (${elapsed}s elapsed, ${remaining}s remaining)"
        fi
    done
    
    return 1
}

# [1/5] Stop old processes
echo ""
echo "[1/5] stop old processes..."
if command -v lsof >/dev/null; then
    backend_procs=$(lsof -t -i:${BACKEND_PORT} 2>/dev/null || true)
    frontend_procs=$(lsof -t -i:${FRONTEND_PORT} 2>/dev/null || true)
    
    if [ -n "$backend_procs" ]; then
        echo "  Killing backend processes on port ${BACKEND_PORT}: ${backend_procs}"
        echo "${backend_procs}" | xargs -r kill -9
    fi
    
    if [ -n "$frontend_procs" ]; then
        echo "  Killing frontend processes on port ${FRONTEND_PORT}: ${frontend_procs}"
        echo "${frontend_procs}" | xargs -r kill -9
    fi
elif command -v netstat >/dev/null; then
    ports_pids=$(netstat -tlnp 2>/dev/null | grep -E ":${BACKEND_PORT}|:${FRONTEND_PORT}" | awk '{print $7}' | cut -d'/' -f1)
    if [ -n "$ports_pids" ]; then
        echo "Killing processes on ports ${BACKEND_PORT}, ${FRONTEND_PORT}: ${ports_pids}"
        echo "${ports_pids}" | xargs -r kill -9 2>/dev/null || true
    fi
fi

sleep 2

# [2/5] Skip MySQL setup for now (use existing configuration)
echo ""
echo "[2/5] skip local MySQL setup"

# [3/5] Start backend
echo ""
echo "[3/5] start backend (timeout: ${TIMEOUT_SECONDS}s)..."
cd "${REPO}/backend"

backend_pid=""
python_cmd=".venv/bin/python"
if ! command -v "${python_cmd}" >/dev/null 2>&1; then
    python_cmd="python3"
fi

"${python_cmd}" -m uvicorn app.main:app \
    --host "${BACKEND_HOST}" \
    --port "${BACKEND_PORT}" \
    --log-level info \
    --no-access-log \
    >"${RUN_DIR}/backend.log" 2>"${RUN_DIR}/backend-error.log" &

backend_pid=$!
echo "  backend PID: ${backend_pid}"

if wait_for_backend_health; then
    echo "✓ Backend started successfully"
else
    echo "❌ Backend failed to start within ${TIMEOUT_SECONDS}s"
    handle_failure
fi

# [4/5] Start frontend
echo ""
echo "[4/5] start frontend (timeout: ${TIMEOUT_SECONDS}s)..."
cd "${REPO}/frontend"

npm_cmd="npm"
if ! command -v npm >/dev/null 2>&1; then
    echo "❌ npm not found"
    handle_failure
fi

"${npm_cmd}" run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" \
    >"${RUN_DIR}/frontend.log" 2>"${RUN_DIR}/frontend-error.log" &

frontend_pid=$!
echo "  frontend PID: ${frontend_pid}"

frontend_ready=false
start_time=$(date +%s)
elapsed=0

while [ $elapsed -lt ${TIMEOUT_SECONDS} ]; do
    if curl -s -o /dev/null -w "%{http_code}" "${frontend_base_url}/" | grep -q "200"; then
        echo "✓ Frontend healthy after ${elapsed}s"
        frontend_ready=true
        break
    fi
    
    sleep $(echo "scale=2; ${CHECK_INTERVAL_MS} / 1000" | bc)
    elapsed=$(($(date +%s) - start_time))
    
    if [ $((elapsed % 5)) -eq 0 ]; then
        remaining=$((TIMEOUT_SECONDS - elapsed))
        echo "  ⏱ Frontend starting... (${elapsed}s elapsed, ${remaining}s remaining)"
    fi
done

if ! ${frontend_ready}; then
    echo "❌ Frontend failed to start within ${TIMEOUT_SECONDS}s"
    handle_failure
fi

# [5/5] Final verification
echo ""
echo "[5/5] verify services..."

if curl -s "${backend_base_url}/api/health" | grep -q '"status":"healthy"'; then
    echo "✓ Backend API responding"
else
    echo "⚠ Backend health check failed"
fi

if curl -s "${frontend_base_url}/" | grep -q "玄穹文枢"; then
    echo "✓ Frontend HTML returned"
else
    echo "⚠ Frontend content check failed"
fi

# Success message
echo ""
echo "=== 启动完成 ==="
echo "URLs:"
echo "  frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "  backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  logs:     ${RUN_DIR}"

# Keep background processes running
exec tail -f /dev/null
