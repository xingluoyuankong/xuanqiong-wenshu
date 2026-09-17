"""
Process manifest utility for tracking child processes.
Records PID, command, start/exit times, and exit codes for troubleshooting.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core.config import settings


class ProcessManifest:
    """Track child processes across application lifecycle."""

    def __init__(self) -> None:
        self.processes: List[Dict[str, Any]] = []
        self.start_time: str = datetime.now().isoformat()
        self._log_dir = settings.runtime_log_dir if hasattr(settings, 'runtime_log_dir') else Path('./logs')
        
    def add_process(
        self,
        pid: int,
        command: str,
        parent_pid: Optional[int] = None,
        process_type: str = "unknown",
        description: str = ""
    ) -> Dict[str, Any]:
        """Record a new subprocess being launched."""
        record = {
            "pid": pid,
            "command": command,
            "parent_pid": parent_pid or os.getpid(),
            "process_type": process_type,
            "description": description,
            "start_time": datetime.now().isoformat(),
            "exit_code": None,
            "exit_reason": None,
            "end_time": None
        }
        self.processes.append(record)
        return record
    
    def remove_process(self, pid: int, exit_code: int, reason: str = "completed") -> None:
        """Record when a subprocess terminates."""
        for proc in self.processes:
            if proc["pid"] == pid:
                proc["exit_code"] = exit_code
                proc["exit_reason"] = reason
                proc["end_time"] = datetime.now().isoformat()
                break
    
    def update_process_status(self, pid: int, exit_code: int, reason: str) -> None:
        """Convenience method to add/remove process in one call."""
        self.remove_process(pid, exit_code, reason)
    
    def get_children_of(self, parent_pid: int) -> List[Dict[str, Any]]:
        """Get all children of a given parent process."""
        return [p for p in self.processes if p.get("parent_pid") == parent_pid]
    
    def get_active_processes(self) -> List[Dict[str, Any]]:
        """Get all processes that haven't exited yet."""
        return [p for p in self.processes if p.get("exit_code") is None]
    
    def get_completed_processes(self) -> List[Dict[str, Any]]:
        """Get all processes that have terminated."""
        return [p for p in self.processes if p.get("exit_code") is not None]
    
    def save(self, filepath: Optional[Path] = None) -> Path:
        """Save manifest to JSON file."""
        if filepath is None:
            filepath = self._log_dir / "current_run.json"
        
        # Ensure directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "manifest_version": "1.0",
            "start_time": self.start_time,
            "end_time": datetime.now().isoformat(),
            "total_processes": len(self.processes),
            "active_count": len(self.get_active_processes()),
            "completed_count": len(self.get_completed_processes()),
            "processes": self.processes
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        return filepath
    
    @classmethod
    def load(cls, filepath: Path) -> "ProcessManifest":
        """Load manifest from JSON file."""
        instance = cls()
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        instance.start_time = data.get("start_time", "")
        instance.processes = data.get("processes", [])
        instance._log_dir = data.get("_log_dir", Path('./logs')) if isinstance(data.get("_log_dir"), str) else Path('./logs')
        
        # Calculate counts based on loaded processes
        instance._count_active = len([p for p in instance.processes if p.get("exit_code") is None])
        instance._count_completed = len([p for p in instance.processes if p.get("exit_code") is not None])
        
        return instance
    
    @property
    def total_processes(self) -> int:
        return len(self.processes)
    
    @property
    def active_count(self) -> int:
        return len(self.get_active_processes())
    
    @property
    def completed_count(self) -> int:
        return len(self.get_completed_processes())


def launch_subprocess_with_manifest(
    manifest: ProcessManifest,
    cmd: List[str],
    process_type: str = "subprocess",
    description: str = "",
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
) -> tuple[int, ProcessManifest]:
    """
    Launch a subprocess and automatically track it in the manifest.
    
    Returns: (pid, manifest)
    """
    from subprocess import Popen, PIPE
    
    command_str = " ".join(cmd)
    parent_pid = os.getpid()
    
    # Launch the process
    proc = Popen(
        cmd,
        stdout=PIPE,
        stderr=PIPE,
        cwd=cwd,
        env=env,
        text=True
    )
    
    # Record in manifest
    manifest.add_process(
        pid=proc.pid,
        command=command_str,
        parent_pid=parent_pid,
        process_type=process_type,
        description=description
    )
    
    return proc.pid, manifest


def cleanup_subprocess_with_manifest(
    proc: Any,
    manifest: ProcessManifest,
    timeout: Optional[int] = None
) -> tuple[int, str]:
    """
    Wait for subprocess to complete and record in manifest.
    
    Returns: (exit_code, reason)
    """
    try:
        proc.wait(timeout=timeout)
        exit_code = proc.returncode
        
        if exit_code == 0:
            reason = "completed_successfully"
        elif exit_code < 0:
            reason = f"terminated_signal_{-exit_code}"
        else:
            reason = f"exited_with_code_{exit_code}"
        
        manifest.remove_process(proc.pid, exit_code, reason)
        return exit_code, reason
        
    except Exception as e:
        # Try to get exit code if available
        exit_code = proc.returncode if proc.returncode is not None else -999
        manifest.remove_process(proc.pid, exit_code, f"error:{str(e)}")
        return exit_code, f"exception:{str(e)}"
