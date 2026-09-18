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

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.process_manager import ProcessManifestManager


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
    
    # Initialize manager
    manager = ProcessManifestManager(args.log_dir)
    
    print(f"Started process manifest manager (PID={manager._manifest.parent_pid})")
    print(f"Log directory: {args.log_dir}")
    print(f"Manifest file: {manager.manifest_path}")
    
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
    backend_proc = manager.spawn_process(backend_cmd, "uvicorn", cwd=str(Path(__file__).parent.parent.parent / "backend"))
    
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
        manager.record_termination(
            backend_proc.pid,
            backend_proc.returncode or -1,
            "health check timeout"
        )
        sys.exit(1)
    
    # Keep this process alive until child exits
    print("\nMonitoring processes... Press Ctrl+C to stop")
    
    try:
        exit_code, reason = manager.wait_and_record(backend_proc, timeout=None, reason="completed normally")
        print(f"\nBackend exited with code {exit_code}: {reason}")
        
    except KeyboardInterrupt:
        print("\nReceived interrupt, terminating backend...")
        manager.terminate_process(backend_proc, "keyboard interrupt")
    
    # Write final manifest summary
    print("\n" + "="*60)
    print("Process Manifest Summary:")
    print("="*60)
    
    manifest = manager.read_manifest()
    if manifest:
        print(f"Parent PID: {manifest.parent_pid}")
        print(f"Spawned at: {manifest.spawned_at}")
        print(f"Total processes spawned: {len(manifest.processes)}")
        
        running = len([p for p in manifest.processes if p.terminated_at is None])
        terminated = len(manifest.processes) - running
        
        print(f"Currently running: {running}")
        print(f"Terminated: {terminated}")
        
        if manifest.processes:
            last = manifest.processes[-1]
            print(f"\nLast process: PID={last.pid}, Name={last.name}")
            if last.terminated_at:
                print(f"Exit code: {last.exit_code}, Reason: {last.termination_reason}")
    
    print("="*60)
    print(f"Full manifest saved to: {manager.manifest_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
