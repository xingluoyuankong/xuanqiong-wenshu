"""Tests for ProcessManifestManager."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.process_manager import ProcessManifest, ProcessInfo, ProcessManifestManager


class TestProcessInfo:
    """Tests for ProcessInfo dataclass."""
    
    def test_process_info_basic(self):
        """Test basic process info creation."""
        info = ProcessInfo(
            pid=12345,
            name="uvicorn",
            command=["uvicorn", "app.main:app"],
            started_at="2026-09-17T18:00:00Z",
        )
        
        assert info.pid == 12345
        assert info.name == "uvicorn"
        assert len(info.command) == 2
    
    def test_process_info_with_termination(self):
        """Test process info with termination details."""
        info = ProcessInfo(
            pid=12346,
            name="npm",
            command=["npm", "run", "dev"],
            started_at="2026-09-17T18:00:01Z",
            terminated_at="2026-09-17T18:05:00Z",
            exit_code=0,
            termination_reason="completed normally",
        )
        
        assert info.terminated_at is not None
        assert info.exit_code == 0
        assert info.termination_reason == "completed normally"


class TestProcessManifest:
    """Tests for ProcessManifest dataclass and serialization."""
    
    def test_manifest_to_dict(self):
        """Test manifest serialization to dictionary."""
        manifest = ProcessManifest(
            parent_pid=1000,
            spawned_at="2026-09-17T18:00:00Z",
            processes=[
                ProcessInfo(pid=1001, name="test", command=["test"], started_at="2026-09-17T18:00:01Z"),
            ],
            parent_child_map={"1001": "1000"},
        )
        
        data = manifest.to_dict()
        
        assert "parent_pid" in data
        assert "spawned_at" in data
        assert "processes" in data
        assert "parent_child_map" in data
        assert len(data["processes"]) == 1
    
    def test_manifest_from_dict(self):
        """Test manifest deserialization from dictionary."""
        data = {
            "parent_pid": 1000,
            "spawned_at": "2026-09-17T18:00:00Z",
            "processes": [
                {"pid": 1001, "name": "test", "command": ["test"], "started_at": "2026-09-17T18:00:01Z"},
            ],
            "parent_child_map": {"1001": "1000"},
        }
        
        manifest = ProcessManifest.from_dict(data)
        
        assert manifest.parent_pid == 1000
        assert len(manifest.processes) == 1
        assert manifest.processes[0].pid == 1001


class TestProcessManifestManager:
    """Tests for ProcessManifestManager class."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_init_creates_directory(self, temp_log_dir):
        """Test that manager creates log directory if missing."""
        subdir = temp_log_dir / "subdir"
        manager = ProcessManifestManager(str(subdir))
        
        assert subdir.exists()
        assert subdir.is_dir()
    
    def test_init_writes_initial_manifest(self, temp_log_dir):
        """Test that initialization writes empty manifest."""
        manager = ProcessManifestManager(str(temp_log_dir))
        
        manifest_path = temp_log_dir / "current_run.json"
        assert manifest_path.exists()
        
        # Load and verify structure
        with open(manifest_path, "r") as f:
            data = json.load(f)
        
        assert data["parent_pid"] == os.getpid()
        assert "spawned_at" in data
        assert len(data["processes"]) == 0
    
    @patch("subprocess.Popen")
    def test_spawn_process_records_in_manifest(self, mock_popen, temp_log_dir):
        """Test that spawning records new process in manifest."""
        mock_proc = mock_popen.return_value
        mock_proc.pid = 12345
        mock_proc.stdout = None
        mock_proc.stderr = None
        
        manager = ProcessManifestManager(str(temp_log_dir))
        
        cmd = ["python", "-m", "uvicorn", "app.main:app"]
        proc = manager.spawn_process(cmd, "uvicorn", cwd="/tmp")
        
        # Verify subprocess.Popen was called correctly
        mock_popen.assert_called_once()
        
        # Read manifest back and verify
        manifest = manager.read_manifest()
        assert manifest is not None
        assert len(manifest.processes) == 1
        assert manifest.processes[0].pid == 12345
        assert manifest.processes[0].name == "uvicorn"
        assert manifest.processes[0].command == cmd
    
    @patch("subprocess.Popen")
    def test_wait_and_record_updates_manifest(self, mock_popen, temp_log_dir):
        """Test that wait_and_record adds termination info."""
        mock_proc = mock_popen.return_value
        mock_proc.pid = 12345
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_proc.stdout = None
        mock_proc.stderr = None
        
        manager = ProcessManifestManager(str(temp_log_dir))
        
        # Spawn process
        proc = manager.spawn_process(["test"], "test")
        
        # Wait and record - note parameter order changed
        exit_code, reason = manager.wait_and_record(proc, reason="completed", timeout_seconds=10)
        
        assert exit_code == 0
        
        # Verify manifest updated
        manifest = manager.read_manifest()
        assert manifest is not None
        assert len(manifest.processes) > 0
        assert manifest.processes[-1].exit_code == 0
        assert manifest.processes[-1].terminated_at is not None
        assert manifest.processes[-1].termination_reason == "completed"
    
    def test_read_nonexistent_manifest_returns_none(self, temp_log_dir):
        """Test reading manifest when file doesn't exist."""
        # Don't create any manifest
        manager = ProcessManifestManager(str(temp_log_dir))
        
        # Remove the initial manifest we just created
        (temp_log_dir / "current_run.json").unlink()
        
        result = manager.read_manifest()
        assert result is None
    
    def test_manifest_persists_across_reads_writes(self, temp_log_dir):
        """Test that manifest persists across multiple reads and writes."""
        manager = ProcessManifestManager(str(temp_log_dir))
        
        # First write
        manager._manifest.processes.append(
            ProcessInfo(pid=100, name="p1", command=["a"], started_at="2026-01-01T00:00:00Z")
        )
        manager.write_manifest()
        
        # Create new manager instance (simulating fresh read)
        manager2 = ProcessManifestManager(str(temp_log_dir))
        
        # Read the persisted manifest from disk
        manifest2 = manager2.read_manifest()
        
        assert manifest2 is not None
        assert len(manifest2.processes) == 1
        assert manifest2.processes[0].pid == 100


def test_no_syntax_errors():
    """Verify module has no Python syntax errors by compiling it."""
    module_path = Path(__file__).parent.parent / "app" / "utils" / "process_manager.py"
    
    with open(module_path, "r") as f:
        source = f.read()
    
    # This will raise SyntaxError if there are syntax issues
    compile(source, str(module_path), "exec")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
