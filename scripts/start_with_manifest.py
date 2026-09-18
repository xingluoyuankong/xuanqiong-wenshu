#!/usr/bin/env python3
"""
Wrapper script to start services with process manifest tracking.
Called by start.ps1 for cross-platform process management.

Usage:
    python scripts/start_with_manifest.py --log-dir /path/to/logs
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add backend to path (app 包位于 backend/ 下)
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.process_manager import (
    get_manifest,
    spawn_child,
    wait_child_exit,
)


def wait_for_health_check(url: str, timeout_seconds: int = 30) -> bool:
    """Wait for a service to become healthy."""
    import urllib.request
    
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            req = urllib.request.urlopen(url, timeout=2)
            if req.getcode() == 200:
                return True
        except Exception:
            pass
        
        time.sleep(0.5)
    
    return False


def main():
    parser = argparse.ArgumentParser(description="Start services with process manifest tracking")
    parser.add_argument("--log-dir", required=True, help="Runtime log directory")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", default="8013")
    parser.add_argument("--frontend-port", default="5174")
    args = parser.parse_args()
    
    # 使用 services/process_manager 的全局单例（唯一生效的 manifest 链路）。
    # 注意：utils/process_manager.ProcessManifestManager 为 legacy 实现，
    # 仅供其自身单测使用，启动流程不再使用，避免两套写同一 current_run.json。
    manifest = get_manifest(log_dir=Path(args.log_dir))
    manifest_path = manifest.write_to_file()

    print(f"Started process manifest (parent PID={manifest.parent_pid})")
    print(f"Log directory: {args.log_dir}")
    print(f"Manifest file: {manifest_path}")
    
    # Start backend
    backend_py = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    
    if not backend_py.exists():
        backend_py = Path(sys.executable)
    
    backend_cmd = [
        str(backend_py),
        "-m", "uvicorn",
        "app.main:app",
        "--host", args.backend_host,
        "--port", args.backend_port,
        "--log-level", "info",
    ]
    
    print(f"\nStarting backend: {' '.join(backend_cmd)}")
    backend_proc = spawn_child(
        backend_cmd,
        # app 包位于 <project_root>/backend 下，uvicorn 需以该目录为 cwd
        cwd=str(Path(__file__).parent.parent / "backend"),
    )
    
    # Wait for health check
    print(f"Waiting for backend health check at http://{args.backend_host}:{args.backend_port}/api/health")
    backend_ready = wait_for_health_check(
        f"http://{args.backend_host}:{args.backend_port}/api/health",
        timeout_seconds=30
    )
    
    if backend_ready:
        print("✓ Backend healthy")
    else:
        print("✗ Backend failed to become healthy")
        wait_child_exit(backend_proc, reason="health check timeout", timeout_seconds=5)
        sys.exit(1)
    
    # Keep this process alive until child exits
    print("\nMonitoring processes... Press Ctrl+C to stop")
    
    try:
        exit_code = wait_child_exit(backend_proc, reason="completed normally")
        print(f"\nBackend exited with code {exit_code}")
        
    except KeyboardInterrupt:
        print("\nReceived interrupt, terminating backend...")
        import signal
        backend_proc.send_signal(signal.SIGTERM)
        wait_child_exit(backend_proc, reason="keyboard interrupt", timeout_seconds=10)
    
    # Write final manifest summary
    print("\n" + "="*60)
    print("Process Manifest Summary:")
    print("="*60)
    
    final_path = manifest.write_to_file()
    print(f"Parent PID: {manifest.parent_pid}")
    print(f"Spawned at: {manifest.timestamp}")
    print(f"Total children spawned: {len(manifest.children)}")
    
    running = len([c for c in manifest.children if c["ended_at"] is None])
    terminated = len(manifest.children) - running
    
    print(f"Currently running: {running}")
    print(f"Terminated: {terminated}")
    
    if manifest.children:
        last = manifest.children[-1]
        print(f"\nLast child: PID={last['pid']}, CMD={last['command']}")
        if last["ended_at"]:
            print(f"Exit code: {last['exit_code']}, Reason: {last['reason']}")
    
    print("="*60)
    print(f"Full manifest saved to: {final_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
