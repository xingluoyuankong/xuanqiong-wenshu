#!/bin/bash
# 玄穹文枢 stop script - Linux/Mac version with zombie process verification
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${SCRIPT_DIR}"
LOGS_ROOT="${REPO}/logs"

echo "=== 停止玄穹文枢服务 (Linux/Mac) ==="

BACKEND_PORT="${XUANQIONG_WENSHU_BACKEND_PORT:-8013}"
FRONTEND_PORT="${XUANQIONG_WENSHU_FRONTEND_PORT:-5174}"

cleanup_orphaned_processes() {
    local backend_pid=$1
    local frontend_pid=$2
    
    echo "Cleaning up orphaned processes..."
    
    if command -v pkill >/dev/null; then
        echo "Stopping uvicorn processes..."
        pkill -f "uvicorn.*${BACKEND_PORT}" 2>/dev/null || true
        sleep 1
        
        echo "Stopping http.server processes..."
        pkill -f "http.server.*${FRONTEND_PORT}" 2>/dev/null || true
    elif command -v kill >/dev/null; then
        [ -n "$backend_pid" ] && [ "$backend_pid" -gt 0 ] && kill -9 "$backend_pid" 2>/dev/null || true
        [ -n "$frontend_pid" ] && [ "$frontend_pid" -gt 0 ] && kill -9 "$frontend_pid" 2>/dev/null || true
    fi
}

cleanup_socket_files() {
    echo ""
    echo "=== Socket 文件清理 ==="
    
    # Clean RUN_DIR sockets
    for sock_pattern in "${RUN_DIR}/uvicorn.sock" "${RUN_DIR}/fastapi.sock"; do
        [ -f "$sock_pattern" ] && rm -f "$sock_pattern" && echo "✓ Removed $sock_pattern"
    done
    
    # Clean /tmp sockets
    find /tmp -maxdepth 1 -name "*.sock" -type f 2>/dev/null | while read -r sock; do
        rm -f "$sock" && echo "✓ Removed stale socket: $sock"
    done || true
    
    echo "✓ Stale sockets cleaned"
}

verify_no_zombies() {
    echo ""
    echo "=== 僵尸进程验证 ==="
    
    zombie_count=0
    
    # Check Python processes
    python_procs=$(pgrep -f "python.*uvicorn|python.*http.server" 2>/dev/null || true)
    if [ -n "$python_procs" ]; then
        echo "⚠ Found orphaned Python processes:"
        for pid in $python_procs; do
            cmd=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ' | cut -c0-100 || echo "unknown")
            echo "  PID=$pid Cmd: $cmd"
            zombie_count=$((zombie_count + 1))
        done
    else
        echo "✓ No orphaned Python processes detected"
    fi
    
    return $zombie_count
}

# Stop old processes
echo ""
echo "[1/2] stop running services..."

if command -v lsof >/dev/null; then
    backend_procs=$(lsof -t -i:${BACKEND_PORT} 2>/dev/null || true)
    frontend_procs=$(lsof -t -i:${FRONTEND_PORT} 2>/dev/null || true)
    
    if [ -n "$backend_procs" ]; then
        echo "Killing backend PIDs: ${backend_procs}"
        echo "${backend_procs}" | xargs -r kill -9 2>/dev/null || true
    fi
    
    if [ -n "$frontend_procs" ]; then
        echo "Killing frontend PIDs: ${frontend_procs}"
        echo "${frontend_procs}" | xargs -r kill -9 2>/dev/null || true
    fi
elif command -v netstat >/dev/null; then
    ports_pids=$(netstat -tlnp 2>/dev/null | grep -E ":${BACKEND_PORT}|:${FRONTEND_PORT}" | awk '{print $7}' | cut -d'/' -f1)
    if [ -n "$ports_pids" ]; then
        echo "Killing port processes: ${ports_pids}"
        echo "${ports_pids}" | xargs -r kill -9 2>/dev/null || true
    fi
fi

sleep 2

# Get current run directory
LATEST_RUN="${LOGS_ROOT}/latest-run.txt"
RUN_DIR=""
if [ -f "$LATEST_RUN" ]; then
    RUN_DIR=$(cat "$LATEST_RUN")
    echo "Using latest run: ${RUN_DIR}"
else
    echo "⚠ No latest-run.txt found"
fi

# Cleanup orphaned processes
if command -v pkill >/dev/null; then
    cleanup_orphaned_processes "" ""
fi

# Verify no zombies
verify_no_zombies

# Clean socket files
cleanup_socket_files

echo ""
echo "=== 停止完成 ==="
echo "僵尸进程数：$zombie_count"
