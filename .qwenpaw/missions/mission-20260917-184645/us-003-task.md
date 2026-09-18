# Task: US-003 - Create Process Manifest on Child Launch

## Story Details
```json
{
  "id": "US-003",
  "title": "Create process manifest on child launch",
  "description": "As a debugger, I need to track child process handles and their exit reasons for troubleshooting.",
  "acceptanceCriteria": [
    "Logs PID, command, and start time for each subprocess",
    "Records exit code and reason when child terminates",
    "Writes manifest to runtime_log_dir/current_run.json",
    "Includes parent-child relationships",
    "No Python syntax errors"
  ]
}
```

## Implementation Requirements

### Files to Create/Modify:
1. **New**: `backend/app/services/process_manifest.py`
2. **Modified**: `backend/app/main.py` (lifespan integration)

### Module Structure: process_manifest.py

```python
"""Process manifest for tracking subprocess lifecycle."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ProcessManifest:
    """Track child process handles and exit reasons."""
    
    def __init__(self, runtime_log_dir: Path, run_id: str):
        self.runtime_log_dir = runtime_log_dir
        self.run_id = run_id
        self.start_time = datetime.utcnow().isoformat() + "Z"
        self.processes: list[dict] = []
        self.exits: list[dict] = []
        self._manifest_path = runtime_log_dir / "current_run.json"
    
    def record_process(self, pid: int, command: str, parent_pid: Optional[int] = None) -> None:
        """Record a new child process launch."""
        entry = {
            "pid": pid,
            "command": command,
            "start_time": datetime.utcnow().isoformat() + "Z",
            "parent_pid": parent_pid,
            "exit_code": None,
            "exit_reason": None,
        }
        self.processes.append(entry)
        logger.info(f"进程启动 | PID={pid} CMD={command}")
    
    def record_exit(
        self, pid: int, exit_code: int, reason: Optional[str] = None
    ) -> None:
        """Record a child process termination."""
        # Update the process entry
        for proc in self.processes:
            if proc["pid"] == pid:
                proc["exit_code"] = exit_code
                proc["exit_reason"] = reason or ("completed" if exit_code == 0 else f"error_{exit_code}")
                break
        
        # Add to exits log
        exit_entry = {
            "pid": pid,
            "exit_code": exit_code,
            "reason": reason or ("completed" if exit_code == 0 else f"error_{exit_code}"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.exits.append(exit_entry)
        logger.info(f"进程终止 | PID={pid} EXIT_CODE={exit_code} REASON={exit_entry['reason']}")
    
    def write_manifest(self) -> bool:
        """Write manifest to JSON file."""
        try:
            self.runtime_log_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "run_id": self.run_id,
                "start_time": self.start_time,
                "processes": self.processes,
                "exits": self.exits,
            }
            with open(self._manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Manifest 已写入：{self._manifest_path}")
            return True
        except Exception as e:
            logger.error(f"写入 manifest 失败：{type(e).__name__}: {e}")
            return False
    
    def sync_and_write(self) -> None:
        """Sync current state and write to file."""
        self.write_manifest()
    
    @classmethod
    def load_from_file(cls, manifest_path: Path) -> Optional["ProcessManifest"]:
        """Load manifest from existing file."""
        if not manifest_path.exists():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Create instance without full init
            instance = cls.__new__(cls)
            instance.run_id = data.get("run_id", "")
            instance.start_time = data.get("start_time", "")
            instance.processes = data.get("processes", [])
            instance.exits = data.get("exits", [])
            instance._manifest_path = manifest_path
            return instance
        except Exception as e:
            logger.error(f"加载 manifest 失败：{type(e).__name__}: {e}")
            return None
```

### Integration Points in main.py

```python
# In lifespan context manager:
async with AsyncSessionLocal() as session:
    # ... existing initialization ...
    runtime_log_dir = settings.runtime_log_dir
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    manifest = ProcessManifest(runtime_log_dir, run_id)
    app.state.process_manifest = manifest
```

### Usage Pattern

```python
# Start subprocess
pid = subprocess.Popen(...).pid
manifest.record_process(pid, command=str(proc_args), parent_pid=os.getpid())

# When done
manifest.record_exit(pid, proc.returncode, reason="completed")
manifest.sync_and_write()
```

## Verification Checklist
- [ ] Run typecheck: `cd backend && python -m mypy app/services/process_manifest.py`
- [ ] No syntax errors
- [ ] Test basic functionality locally
- [ ] Commit with message: `feat: US-003 - Create process manifest on child launch`
- [ ] Append progress to `.qwenpaw/missions/.../progress.txt`
