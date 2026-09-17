"""Tests for cleanup module - US-004: Implement graceful failure cleanup."""

import pytest
from pathlib import Path
import tempfile
import os

# Import the cleanup module
from app.cleanup import (
    find_process_by_port,
    stop_process,
    cleanup_socket_files,
    verify_no_zombie_processes,
    perform_graceful_cleanup,
)


class TestCleanupSocketFiles:
    """Test socket file cleanup functionality."""
    
    def test_cleans_existing_socket_files(self):
        """Verify that existing .sock files are removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            
            # Create some fake socket files
            sock1 = run_dir / "uvicorn.sock"
            sock2 = run_dir / "fastapi.socket"
            sock1.touch()
            sock2.touch()
            
            cleaned = cleanup_socket_files(run_dir)
            
            assert len(cleaned) == 2
            assert not sock1.exists()
            assert not sock2.exists()
    
    def test_handles_missing_directory(self):
        """Test behavior when directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = Path(tmpdir) / "nonexistent"
            # Should not raise exception
            cleaned = cleanup_socket_files(non_existent)
            assert cleaned == []


class TestFindProcessByPort:
    """Test process discovery by port."""
    
    def test_returns_none_for_unused_port(self):
        """Verify we get None when port is free."""
        pid = find_process_by_port(0)  # Port 0 is always invalid
        assert pid is None or pid <= 0


class TestGracefulCleanup:
    """Test comprehensive cleanup workflow."""
    
    def test_cleanup_report_structure(self):
        """Verify cleanup returns expected structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = perform_graceful_cleanup(
                backend_pid=None,
                frontend_pid=None,
                repo_path=tmpdir,
                run_dir=tmpdir,
                ports=[8013, 5174]
            )
            
            assert 'backend_stopped' in result
            assert 'frontend_stopped' in result
            assert 'sockets_cleaned' in result
            assert 'remaining_orphans' in result
            assert 'ports_free' in result
            assert 'errors' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
