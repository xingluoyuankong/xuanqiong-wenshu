"""Process tracking and manifest management for debugging orphan processes."""

import json
import os
import signal
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class ChildProcess:
    """Represents a tracked child process."""

    pid: int
    command: str
    description: str
    start_time: str = ""
    exit_code: Optional[int] = None
    exit_reason: Optional[str] = None
    parent_pid: Optional[int] = None

    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.now(timezone.utc).isoformat()


class ProcessTracker:
    """Track child processes and write runtime manifests."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.child_processes: dict[int, ChildProcess] = {}
        self._manifest_path = log_dir / "current_run.json"

    def ensure_log_dir(self) -> None:
        """Ensure the log directory exists."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_child(
        self,
        pid: int,
        command: str,
        description: str,
        parent_pid: Optional[int] = None,
    ) -> ChildProcess:
        """Record when launching a subprocess."""
        child = ChildProcess(
            pid=pid,
            command=command,
            description=description,
            parent_pid=parent_pid or os.getpid(),
        )
        self.child_processes[pid] = child
        self.write_manifest()
        return child

    def record_exit(
        self, pid: int, exit_code: Optional[int], reason: Optional[str]
    ) -> None:
        """Record termination of a tracked child."""
        if pid in self.child_processes:
            child = self.child_processes[pid]
            child.exit_code = exit_code
            child.exit_reason = reason or ("Normal termination" if exit_code == 0 else "Unknown")
            # Update end time in start_time field for simplicity
            child.start_time += f" (ended {datetime.now(timezone.utc).isoformat()})"
            self.write_manifest()

    def get_child(self, pid: int) -> Optional[ChildProcess]:
        """Get child process info by PID."""
        return self.child_processes.get(pid)

    def list_active(self) -> list[ChildProcess]:
        """Get all active (not exited) children."""
        return [c for c in self.child_processes.values() if c.exit_code is None]

    def list_terminated(self) -> list[ChildProcess]:
        """Get all terminated children."""
        return [c for c in self.child_processes.values() if c.exit_code is not None]

    def kill_all(self, signal_num: int = signal.SIGTERM) -> None:
        """Kill all active child processes."""
        for child in self.list_active():
            try:
                os.kill(child.pid, signal_num)
            except OSError:
                pass  # Process may have already died

    def _serialize(self) -> dict[str, Any]:
        """Serialize manifest to JSON-serializable dict."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "child_processes": [asdict(c) for c in self.child_processes.values()],
            "summary": {
                "total_children": len(self.child_processes),
                "active": len(self.list_active()),
                "terminated": len(self.list_terminated()),
            },
        }

    def write_manifest(self) -> None:
        """Write manifest to runtime_log_dir/current_run.json."""
        self.ensure_log_dir()
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._serialize(), f, indent=2, ensure_ascii=False)

    def load_manifest(self) -> Optional[dict[str, Any]]:
        """Load existing manifest if present."""
        if not self._manifest_path.exists():
            return None
        with open(self._manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)


# Global tracker instance
_tracker: Optional[ProcessTracker] = None


def get_tracker(log_dir: Optional[Path] = None) -> ProcessTracker:
    """Get or create global tracker instance."""
    global _tracker
    if _tracker is None:
        from backend.app.core.config import settings

        log_dir = settings.resolved_log_dir
        _tracker = ProcessTracker(log_dir)
    return _tracker


def reset_tracker() -> None:
    """Reset global tracker (for testing)."""
    global _tracker
    _tracker = None
