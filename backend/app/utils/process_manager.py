"""
Process manifest manager for tracking child process lifecycle.
Written as a Python module to be called from start.ps1 and other startup scripts.

This provides:
- Spawning processes with PID recording
- Tracking termination events
- Writing persistent JSON manifests
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ProcessInfo:
    """Information about a spawned process."""
    pid: int
    name: str
    command: list[str]
    started_at: str
    terminated_at: str | None = None
    exit_code: int | None = None
    termination_reason: str | None = None


@dataclass
class ProcessManifest:
    """Complete manifest of the current run's processes."""
    parent_pid: int
    spawned_at: str
    processes: list[ProcessInfo] = field(default_factory=list)
    parent_child_map: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_pid": self.parent_pid,
            "spawned_at": self.spawned_at,
            "processes": [asdict(p) for p in self.processes],
            "parent_child_map": self.parent_child_map,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessManifest":
        processes = [
            ProcessInfo(**p) if isinstance(p, dict) else p
            for p in data.get("processes", [])
        ]
        return cls(
            parent_pid=data["parent_pid"],
            spawned_at=data["spawned_at"],
            processes=processes,
            parent_child_map=data.get("parent_child_map", {}),
        )


class ProcessManifestManager:
    """Manages process spawning, tracking, and manifest persistence."""
    
    def __init__(self, log_dir: str):
        """Initialize with runtime log directory."""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Current run manifest
        self._manifest = ProcessManifest(
            parent_pid=os.getpid(),
            spawned_at=datetime.now(timezone.utc).isoformat(),
        )
        self._lock = threading.Lock()
        
        # Write initial manifest
        self.write_manifest()
    
    def spawn_process(
        self,
        cmd: list[str],
        name: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[Any]:
        """
        Spawn a process and record it in the manifest.
        
        Args:
            cmd: Command and arguments
            name: Short name for logging
            cwd: Working directory (optional)
            env: Environment variables override (optional)
            
        Returns:
            subprocess.Popen object representing the spawned process
            
        Side Effects:
            - Records new entry in manifest.json immediately
        """
        # Convert to absolute path if relative
        if cwd and not os.path.isabs(cwd):
            cwd = os.path.abspath(cwd)
        
        # Build environment with overrides
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        
        # Start the process
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        
        pid = proc.pid
        
        # Record in manifest
        with self._lock:
            self._manifest.processes.append(
                ProcessInfo(
                    pid=pid,
                    name=name,
                    command=list(cmd),
                    started_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        
        # Persist immediately
        self.write_manifest()
        
        return proc
    
    def wait_and_record(
        self,
        proc: subprocess.Popen[Any],
        reason: str = "completed normally",
        timeout_seconds: int | None = None,
    ) -> tuple[int | None, str]:
        """
        Wait for process to complete and record termination details.
        
        Args:
            proc: Popen object to wait on
            timeout_seconds: Optional timeout (None = wait forever)
            reason: Human-readable reason for termination
            
        Returns:
            Tuple of (exit_code, reason)
            
        Side Effects:
            - Updates manifest with termination info
            - Persists manifest to disk
        """
        try:
            exit_code = proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            exit_code = -1
            reason = f"terminated after timeout ({timeout_seconds}s)"
        
        # Update manifest
        with self._lock:
            terminated = False
            for p in self._manifest.processes:
                if p.pid == proc.pid:
                    p.terminated_at = datetime.now(timezone.utc).isoformat()
                    p.exit_code = exit_code
                    p.termination_reason = reason
                    terminated = True
                    break
            
            if not terminated:
                # Shouldn't happen, but handle gracefully
                print(f"WARNING: Process PID {proc.pid} not found in manifest", file=sys.stderr)
        
        self.write_manifest()
        return exit_code, reason
    
    def terminate_process(
        self,
        proc: subprocess.Popen[Any],
        reason: str = "explicitly terminated",
    ) -> tuple[int | None, str]:
        """
        Terminate a running process and record in manifest.
        
        Args:
            proc: Popen object to terminate
            reason: Why we're terminating
            
        Returns:
            Tuple of (exit_code, reason)
            
        Side Effects:
            - Sends SIGTERM (then SIGKILL if needed)
            - Updates manifest with termination info
        """
        try:
            proc.terminate()
            try:
                exit_code, _ = self.wait_and_record(proc, timeout=5, reason=reason)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                exit_code = -9
                self.record_termination(
                    proc.pid,
                    -9,
                    f"{reason}; SIGKILL after SIGTERM timeout",
                )
        except Exception as e:
            print(f"Error terminating process: {e}", file=sys.stderr)
            self.record_termination(proc.pid, -1, f"{reason}: {type(e).__name__}")
        
        return proc.returncode, reason
    
    def record_termination(
        self,
        pid: int,
        exit_code: int,
        reason: str,
    ) -> None:
        """
        Record process termination in manifest.
        
        Args:
            pid: Process ID
            exit_code: Exit code or -1 if killed
            reason: Human-readable explanation
        """
        with self._lock:
            terminated = False
            for p in self._manifest.processes:
                if p.pid == pid:
                    p.terminated_at = datetime.now(timezone.utc).isoformat()
                    p.exit_code = exit_code
                    p.termination_reason = reason
                    terminated = True
                    break
            
            if not terminated:
                # Add missing entry
                self._manifest.processes.append(
                    ProcessInfo(
                        pid=pid,
                        name="unknown",
                        command=[],
                        started_at="",
                        terminated_at=datetime.now(timezone.utc).isoformat(),
                        exit_code=exit_code,
                        termination_reason=reason,
                    )
                )
        
        self.write_manifest()
    
    def write_manifest(self) -> None:
        """Write manifest to current_run.json in log directory."""
        filepath = self.log_dir / "current_run.json"
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._manifest.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"ERROR: Failed to write manifest: {e}", file=sys.stderr)
    
    def read_manifest(self) -> ProcessManifest | None:
        """Read existing manifest from disk.
        
        Note: This reads FROM disk and returns a new ProcessManifest object.
        It does NOT modify self._manifest or return self._manifest.
        Use load_manifest_from_disk() if you want to update the current instance.
        """
        filepath = self.log_dir / "current_run.json"
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ProcessManifest.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Failed to read manifest: {e}", file=sys.stderr)
            return None
    
    def load_manifest_from_disk(self) -> ProcessManifest | None:
        """Load and replace current manifest with persisted version."""
        loaded = self.read_manifest()
        if loaded:
            with self._lock:
                self._manifest = loaded
        return loaded
    
    @property
    def manifest_path(self) -> Path:
        """Path to the manifest file."""
        return self.log_dir / "current_run.json"
    
    @property
    def running_processes(self) -> list[ProcessInfo]:
        """Get list of processes that haven't terminated yet."""
        with self._lock:
            return [p for p in self._manifest.processes if p.terminated_at is None]
