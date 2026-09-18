"""
Process Monitor Module - Tracks subprocess lifecycle for US-003 & US-004.

Records PID, command, start time, exit code, and parent-child relationships.
Writes manifest to runtime_log_dir/current_run.json.
"""

import json
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class ProcessInfo:
    """Container for process information."""
    
    def __init__(self, pid: int, command: str, parent_pid: Optional[int] = None):
        self.pid = pid
        self.command = command
        self.parent_pid = parent_pid
        self.start_time = datetime.now().isoformat()
        self.end_time: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.status: str = "running"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "command": self.command,
            "parent_pid": self.parent_pid,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "exit_code": self.exit_code,
            "status": self.status,
        }


class ProcessMonitor:
    """Monitors subprocesses and writes manifest to runtime log directory."""
    
    def __init__(self, runtime_log_dir: Path):
        """Initialize monitor with target runtime log directory."""
        self.runtime_log_dir = runtime_log_dir
        self.runtime_log_dir.mkdir(parents=True, exist_ok=True)
        
        self.processes: Dict[int, ProcessInfo] = {}
        self.parent_map: Dict[int, int] = {}  # child_pid -> parent_pid
        self.child_map: Dict[int, List[int]] = {}  # parent_pid -> [child_pids]
        
        logger.info("📊 ProcessMonitor initialized at %s", runtime_log_dir)
    
    def _get_process_command(self, pid: int) -> str:
        """Get command string for a given PID (cross-platform)."""
        try:
            if sys.platform == "win32":
                cmd = ["powershell", "-Command", f"(Get-Process -Id {pid}).CommandLine"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                return result.stdout.strip() or "N/A"
            else:
                cmdline_path = Path(f"/proc/{pid}/cmdline")
                if cmdline_path.exists():
                    return " ".join(cmdline_path.read_text().split("\x00"))
        except Exception as e:
            logger.debug("Could not fetch command for PID=%d: %s", pid, e)
        
        return "unknown"
    
    def on_child_launch(self, child_pid: int, command: Optional[str] = None, parent_pid: Optional[int] = None):
        """
        Called when a child process is launched (US-003).
        
        Logs PID, command, start time, and records parent-child relationship.
        """
        if child_pid in self.processes:
            logger.warning("Process PID=%d already tracked", child_pid)
            return
        
        effective_parent = parent_pid or os.getpid()
        cmd_str = command or self._get_process_command(child_pid)
        
        proc_info = ProcessInfo(pid=child_pid, command=cmd_str, parent_pid=effective_parent)
        self.processes[child_pid] = proc_info
        self.parent_map[child_pid] = effective_parent
        
        # Update child map for parent
        if effective_parent not in self.child_map:
            self.child_map[effective_parent] = []
        self.child_map[effective_parent].append(child_pid)
        
        logger.info(
            "🚀 Child launched | PID=%d CMD=%s PARENT_PID=%d START=%s",
            child_pid, cmd_str[:100], effective_parent, proc_info.start_time
        )
        
        self._write_manifest()
    
    def on_child_terminate(
        self, 
        terminated_pid: int, 
        exit_code: Optional[int] = None, 
        reason: Optional[str] = None
    ):
        """
        Called when a child process terminates (US-003).
        
        Records exit code and termination reason.
        """
        if terminated_pid not in self.processes:
            logger.warning("Unknown terminated PID=%d", terminated_pid)
            return
        
        proc_info = self.processes[terminated_pid]
        proc_info.end_time = datetime.now().isoformat()
        proc_info.exit_code = exit_code
        proc_info.status = "exited"
        
        exit_reason = reason or f"code={exit_code}"
        logger.info(
            "💀 Child terminated | PID=%d EXIT=%s REASON=%s",
            terminated_pid, exit_reason, proc_info.end_time
        )
        
        self._write_manifest()
    
    def update_status(self, pid: int, status: str):
        """Update process status (e.g., 'error', 'killed')."""
        if pid in self.processes:
            self.processes[pid].status = status
            logger.info("Status updated for PID=%d to %s", pid, status)
            self._write_manifest()
    
    def get_children(self, parent_pid: int) -> List[int]:
        """Get list of child PIDs for a given parent."""
        return self.child_map.get(parent_pid, [])
    
    def get_all_children(self, parent_pid: int, recursive: bool = False) -> List[int]:
        """Get all descendants of a parent process (optionally recursive)."""
        if not recursive:
            return self.get_children(parent_pid)
        
        all_descendants = []
        children = self.get_children(parent_pid)
        for child in children:
            all_descendants.append(child)
            all_descendants.extend(self.get_all_children(child, recursive=True))
        return all_descendants
    
    def _write_manifest(self):
        """Write current state to runtime_log_dir/current_run.json (US-003)."""
        manifest = {
            "parent_pid": os.getpid(),
            "timestamp": datetime.now().isoformat(),
            "process_count": len(self.processes),
            "processes": [info.to_dict() for info in self.processes.values()],
            "relationships": {
                "parent_map": dict(self.parent_map),
                "child_map": {str(k): v for k, v in self.child_map.items()}
            }
        }
        
        manifest_path = self.runtime_log_dir / "current_run.json"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug("Manifest written to %s", manifest_path)
        except Exception as e:
            logger.error("Failed to write manifest: %s", e)
    
    def finalize(self):
        """Finalize monitoring session and write final manifest."""
        self.update_status(os.getpid(), "finalized")
        logger.info("🏁 Process monitoring finalized")
        self._write_manifest()


def track_subprocess(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    monitor: Optional[ProcessMonitor] = None,
) -> subprocess.Popen:
    """
    Launch subprocess with automatic tracking (US-003 integration).
    
    Usage:
        monitor = ProcessMonitor(Path("/path/to/logs"))
        proc = track_subprocess(["python", "app.py"], monitor=monitor)
    """
    if monitor is None:
        logger.warning("No monitor provided - subprocess will not be tracked")
        return subprocess.Popen(cmd, cwd=cwd, env=env)
    
    proc = subprocess.Popen(cmd, cwd=cwd, env=env)
    
    # Register launch event
    monitor.on_child_launch(
        child_pid=proc.pid,
        command=" ".join(cmd),
        parent_pid=os.getpid()
    )
    
    return proc


def monitor_wrapper(
    cmd: List[str],
    monitor: ProcessMonitor,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> int:
    """
    Run subprocess and automatically record termination (US-003 helper).
    
    Returns exit code, or -1 if error occurred.
    """
    try:
        proc = track_subprocess(cmd, cwd=cwd, env=env, monitor=monitor)
        exit_code = proc.wait()
        
        monitor.on_child_terminate(
            terminated_pid=proc.pid,
            exit_code=exit_code,
            reason=f"normal_exit"
        )
        
        return exit_code
    except Exception as e:
        logger.error("Subprocess failed: %s", e)
        return -1


# Export public API
__all__ = [
    "ProcessMonitor",
    "ProcessInfo",
    "track_subprocess",
    "monitor_wrapper",
]
