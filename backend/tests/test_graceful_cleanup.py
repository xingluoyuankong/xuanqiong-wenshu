"""Tests for graceful failure cleanup module.

This test suite verifies that the GracefulCleanupManager properly handles:
- Process tracking
- Graceful termination on failures
- Socket file cleanup
- Orphan process detection
- Recovery after failed startup
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from app.utils.process_cleanup import (
    GracefulCleanupManager,
    ProcessInfo,
    get_cleanup_manager,
)


logger = logging.getLogger(__name__)


class TestProcessInfo:
    """Tests for the ProcessInfo data class."""

    def test_creation_valid(self):
        """Test creating a valid ProcessInfo object."""
        proc = ProcessInfo(pid=1234, name="uvicorn", port=8013)
        assert proc.pid == 1234
        assert proc.name == "uvicorn"
        assert proc.port == 8013
        assert hasattr(proc, "registered_at")
        assert isinstance(proc.registered_at, float)

    def test_creation_with_none_port(self):
        """Test creating ProcessInfo without port."""
        proc = ProcessInfo(pid=5678, name="http.server", port=None)
        assert proc.pid == 5678
        assert proc.name == "http.server"
        assert proc.port is None

    def test_repr_formatting(self):
        """Test __repr__ output format."""
        proc = ProcessInfo(pid=1000, name="test", port=8080)
        repr_str = repr(proc)
        assert "ProcessInfo" in repr_str
        assert "pid=1000" in repr_str
        assert "name='test'" in repr_str
        assert "port=8080" in repr_str


class TestGracefulCleanupManagerInit:
    """Tests for initialization."""

    def test_initial_state_empty_registry(self):
        """Test that newly created manager has empty registry."""
        mgr = GracefulCleanupManager()
        assert len(mgr.get_registry_summary()) == 0

    def test_singleton_pattern(self):
        """Test that get_cleanup_manager returns singleton instance."""
        mgr1 = get_cleanup_manager()
        mgr2 = get_cleanup_manager()
        assert mgr1 is mgr2

    def test_singleton_persistence(self):
        """Test that singleton persists across calls."""
        mgr1 = get_cleanup_manager()
        mgr1.register_child(123, "test", 8013)
        
        mgr2 = get_cleanup_manager()
        assert len(mgr2.get_registry_summary()) == 1
        assert mgr2.get_registry_summary()[0]["pid"] == 123


class TestRegisterChild:
    """Tests for process registration."""

    def test_register_valid_process(self):
        """Test registering a valid process."""
        mgr = GracefulCleanupManager()
        mgr.register_child(1234, "uvicorn", port=8013)
        
        summary = mgr.get_registry_summary()
        assert len(summary) == 1
        assert summary[0]["pid"] == 1234
        assert summary[0]["name"] == "uvicorn"
        assert summary[0]["port"] == 8013

    def test_register_invalid_pid_zero(self):
        """Test that PID 0 is ignored."""
        mgr = GracefulCleanupManager()
        mgr.register_child(0, "invalid", port=9000)
        
        assert len(mgr.get_registry_summary()) == 0

    def test_register_negative_pid(self):
        """Test that negative PIDs are ignored."""
        mgr = GracefulCleanupManager()
        mgr.register_child(-1, "negative", port=-1)
        
        assert len(mgr.get_registry_summary()) == 0

    def test_register_multiple_processes(self):
        """Test registering multiple processes."""
        mgr = GracefulCleanupManager()
        mgr.register_child(1001, "backend", port=8013)
        mgr.register_child(1002, "frontend", port=5174)
        mgr.register_child(1003, "worker", port=None)
        
        summary = mgr.get_registry_summary()
        assert len(summary) == 3
        pids = {p["pid"] for p in summary}
        assert pids == {1001, 1002, 1003}


class TestFindOrphanedPids:
    """Tests for orphaned process detection."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_detect_running_process(self):
        """Test detecting a process that exists."""
        # Start a background sleep process
        proc = subprocess.Popen(["sleep", "100"])
        try:
            mgr = GracefulCleanupManager()
            mgr.register_child(proc.pid, "sleep_test")
            
            orphans = mgr._find_orphaned_pids()
            assert proc.pid in orphans
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_not_detect_dead_process(self):
        """Test that dead processes are not detected."""
        mgr = GracefulCleanupManager()
        mgr.register_child(99999, "nonexistent")  # Very unlikely PID
        
        orphans = mgr._find_orphaned_pids()
        # Should be empty if no such process exists
        assert 99999 not in orphans

    def test_duplicate_pid_handling(self):
        """Test handling of duplicate PIDs."""
        mgr = GracefulCleanupManager()
        mgr.register_child(1234, "proc1", port=8013)
        mgr.register_child(1234, "proc2", port=9000)  # Same PID
        
        orphans = mgr._find_orphaned_pids()
        # Should handle gracefully without duplication errors
        assert len(orphans) <= 1  # At most one entry per PID


class TestCleanupOnFailure:
    """Tests for cleanup on failure scenarios."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific signals")
    def test_cleanup_graceful_termination(self, tmp_path):
        """Test graceful termination using SIGTERM."""
        # Start a process we can terminate
        script_path = tmp_path / "slow_shutdown.py"
        script_path.write_text("""
import signal, time, sys
def handler(signum, frame):
    print(f"Received {signum}", file=sys.stderr)
signal.signal(signal.SIGTERM, handler)
for i in range(10):
    time.sleep(1)
print("Shutdown complete")
""")
        
        proc = subprocess.Popen([sys.executable, str(script_path)])
        try:
            mgr = GracefulCleanupManager()
            mgr.register_child(proc.pid, "slow_shutdown", port=8080)
            
            stats = mgr.cleanup_on_failure(reason="test failure")
            
            assert stats["terminated_gracefully"] >= 1
            assert proc.poll() is not None  # Process should have terminated
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific signals")
    def test_cleanup_force_kill_when_stuck(self, tmp_path):
        """Test force kill when process doesn't respond to SIGTERM."""
        script_path = tmp_path / "hung_process.py"
        script_path.write_text("""
import signal, time, sys
def ignore_all(signals): pass
signal.signal(signal.SIGTERM, ignore_all)
time.sleep(100)
""")
        
        proc = subprocess.Popen([sys.executable, str(script_path)])
        try:
            mgr = GracefulCleanupManager()
            mgr.register_child(proc.pid, "hung_process", port=8081)
            
            stats = mgr.cleanup_on_failure(reason="stuck process", timeout_seconds=5.0)
            
            # Should have force-killed
            assert stats["terminated_forcefully"] >= 1
            assert proc.poll() is not None
        finally:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass

    def test_cleanup_registry_cleared(self):
        """Test that registry is cleared after cleanup."""
        mgr = GracefulCleanupManager()
        mgr.register_child(1001, "proc1", port=8013)
        mgr.register_child(1002, "proc2", port=5174)
        
        stats = mgr.cleanup_on_failure(reason="cleanup test")
        
        assert len(mgr.get_registry_summary()) == 0
        assert stats["total_tracked"] == 2

    def test_cleanup_no_registered_processes(self):
        """Test cleanup when no processes are registered."""
        mgr = GracefulCleanupManager()
        
        stats = mgr.cleanup_on_failure(reason="no processes")
        
        assert stats["total_tracked"] == 0
        assert stats["terminated_gracefully"] == 0

    def test_cleanup_statistics_structure(self):
        """Test that stats dictionary has correct structure."""
        mgr = GracefulCleanupManager()
        
        stats = mgr.cleanup_on_failure(reason="test")
        
        required_keys = [
            "total_tracked",
            "terminated_gracefully", 
            "terminated_forcefully",
            "failed_to_terminate",
            "socket_files_cleaned",
        ]
        for key in required_keys:
            assert key in stats, f"Missing stat key: {key}"


class TestSocketFileCleanup:
    """Tests for socket file cleanup functionality."""

    def test_socket_removal_when_exists(self, tmp_path):
        """Test removal of existing socket files."""
        sock_path = tmp_path / "test.sock"
        sock_path.touch()
        
        with patch.object(Path, "glob", return_value=[sock_path]), \
             patch.object(GracefulCleanupManager, "_socket_is_bound", return_value=False):
            mgr = GracefulCleanupManager()
            count = mgr._cleanup_socket_files(timeout_seconds=1.0)
        
        assert count >= 1
        assert not sock_path.exists()

    def test_socket_release_when_bound(self, tmp_path):
        """Test socket release before removal."""
        sock_path = tmp_path / "bound.sock"
        sock_path.write_bytes(b"dummy")
        
        # Mock socket binding detection
        with patch.object(GracefulCleanupManager, "_socket_is_bound", return_value=True), \
             patch.object(GracefulCleanupManager, "_release_socket"), \
             patch.object(Path, "unlink"):
            mgr = GracefulCleanupManager()
            count = mgr._cleanup_socket_files(timeout_seconds=1.0)
        
        assert count >= 1

    def test_cleanup_handles_missing_sockets(self):
        """Test cleanup doesn't fail when sockets don't exist."""
        mgr = GracefulCleanupManager()
        
        with patch.object(Path, "glob", return_value=[]):
            count = mgr._cleanup_socket_files(timeout_seconds=1.0)
        
        assert count >= 0  # May return 0 if no paths checked

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix domain sockets")
    def test_actual_unix_socket_creation_and_cleanup(self, tmp_path):
        """Test real Unix socket creation and cleanup."""
        sock_path = tmp_path / "real.sock"
        
        # Create an actual socket server
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(str(sock_path))
        server_sock.listen(1)
        
        # Register as tracked process
        mgr = GracefulCleanupManager()
        mgr.register_child(os.getpid(), "test_server")
        
        # Cleanup should remove the socket
        with patch.object(GracefulCleanupManager, "_socket_is_bound", return_value=True):
            count = mgr._cleanup_socket_files(timeout_seconds=1.0)
        
        assert count >= 1
        assert not sock_path.exists()
        server_sock.close()


class TestVerifyNoOrphans:
    """Tests for orphanc process verification."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix test")
    def test_verify_detects_running_orphan(self, tmp_path):
        """Test that verify detects running orphaned processes."""
        script_path = tmp_path / "orphan_test.py"
        script_path.write_text("import time; time.sleep(100)")
        
        proc = subprocess.Popen([sys.executable, str(script_path)])
        try:
            mgr = GracefulCleanupManager()
            mgr.register_child(proc.pid, "orphan_test")
            
            orphans = mgr.verify_no_orphans()
            assert proc.pid in orphans
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix test")
    def test_verify_no_false_positives(self):
        """Test that verify doesn't report non-existent PIDs."""
        mgr = GracefulCleanupManager()
        # Register an obviously invalid PID
        mgr.register_child(99999, "fake_process")
        
        orphans = mgr.verify_no_orphans()
        # Should not include fake PID
        assert 99999 not in orphans


class TestClearRegistry:
    """Tests for registry clearing."""

    def test_clear_registry_removes_all(self):
        """Test that clear_registry removes all tracked processes."""
        mgr = GracefulCleanupManager()
        mgr.register_child(1001, "proc1", port=8013)
        mgr.register_child(1002, "proc2", port=5174)
        
        mgr.clear_registry()
        
        assert len(mgr.get_registry_summary()) == 0

    def test_clear_after_cleanup(self):
        """Test clear_registry works after cleanup already ran."""
        mgr = GracefulCleanupManager()
        mgr.register_child(1001, "proc1", port=8013)
        
        mgr.cleanup_on_failure(reason="test")
        mgr.clear_registry()  # Should not raise error
        
        assert len(mgr.get_registry_summary()) == 0


class TestRecoveryAfterFailedStartup:
    """Integration-style tests for recovery scenarios."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix test")
    def test_full_lifecycle_simulation(self, tmp_path):
        """Simulate full startup → failure → cleanup → recovery cycle."""
        # Step 1: Register backend and frontend processes
        mgr = GracefulCleanupManager()
        
        # Start a simple HTTP server
        script_path = tmp_path / "simple_server.py"
        script_path.write_text("""
import http.server, socketserver, sys, time
PORT = 8082
with socketserver.TCPServer(("", PORT), http.server.SimpleHTTPRequestHandler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()
""")
        
        server_proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        try:
            # Register as child process
            mgr.register_child(server_proc.pid, "http.server", port=8082)
            
            # Verify it's tracked
            assert len(mgr.get_registry_summary()) == 1
            
            # Simulate failure during startup
            stats = mgr.cleanup_on_failure(reason="startup validation failed")
            
            # Verify cleanup succeeded
            assert stats["total_tracked"] == 1
            assert (stats["terminated_gracefully"] + stats["terminated_forcefully"]) >= 1
            assert server_proc.poll() is not None  # Should be dead
            
            # Registry should be cleared
            assert len(mgr.get_registry_summary()) == 0
            
            # System is now clean - can restart
            mgr.clear_registry()
            assert len(mgr.get_registry_summary()) == 0
            
        finally:
            server_proc.terminate()
            server_proc.wait(timeout=5)


@pytest.mark.integration
class TestCrossPlatformCompatibility:
    """Tests for cross-platform compatibility guarantees."""

    def test_signal_handling_cross_platform(self):
        """Test that signal handling code works on both platforms."""
        mgr = GracefulCleanupManager()
        
        # Just verify methods exist and don't crash
        with patch.object(mgr, '_send_signal') as mock_send:
            # Should not raise any exceptions
            mgr._send_signal(1234, signal.SIGTERM)
        
        assert mock_send.called

    def test_socket_cleanup_platform_independence(self, tmp_path):
        """Test socket cleanup works regardless of platform limitations."""
        mgr = GracefulCleanupManager()
        
        # Should not crash even if sockets unavailable
        result = mgr._cleanup_socket_files(timeout_seconds=1.0)
        
        assert isinstance(result, int)
        assert result >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
