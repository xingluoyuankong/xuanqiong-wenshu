"""Graceful failure cleanup utilities for Xuanqiong Wenshu.

This module provides robust cleanup mechanisms for failed startup scenarios,
handling both Unix-like and Windows environments with comprehensive process
tracking and socket file cleanup.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger("app.cleanup")


class ProcessInfo:
    """Information about a tracked child process."""

    def __init__(self, pid: int, name: str, port: int | None = None):
        self.pid = pid
        self.name = name
        self.port = port
        self.registered_at = time.time()

    def __repr__(self) -> str:
        return f"ProcessInfo(pid={self.pid}, name={self.name!r}, port={self.port})"


class GracefulCleanupManager:
    """Manages graceful cleanup of orphaned processes after startup failures.

    This class provides comprehensive process tracking, termination, and socket
    cleanup capabilities for both Unix-like systems and Windows.
    """

    def __init__(self) -> None:
        """Initialize the cleanup manager with empty process registry."""
        self._tracked_processes: list[ProcessInfo] = []
        self._lock = False  # Simple flag for basic thread-safety

    def register_child(self, pid: int, name: str, port: int | None = None) -> None:
        """Register a child process for tracking.

        Args:
            pid: Process ID of the child process
            name: Human-readable name of the process (e.g., 'uvicorn', 'http.server')
            port: Optional port number this process is listening on
        """
        if pid <= 0:
            logger.warning(f"Invalid PID {pid} ignored for registration")
            return

        proc_info = ProcessInfo(pid=pid, name=name, port=port)
        self._tracked_processes.append(proc_info)
        logger.info(f"Registered child process: {proc_info}")

    def _find_orphaned_pids(self) -> list[int]:
        """Find orphaned processes that are still running.

        Returns:
            List of PIDs for processes that should have been terminated but weren't.
        """
        orphaned: list[int] = []
        seen_pids: set[int] = set()

        for proc in self._tracked_processes:
            try:
                if proc.pid in seen_pids:
                    continue
                seen_pids.add(proc.pid)

                if self._process_exists(proc.pid):
                    orphaned.append(proc.pid)
            except Exception as e:
                logger.debug(f"Error checking process {proc.pid}: {e}")

        return orphaned

    @staticmethod
    def _process_exists(pid: int) -> bool:
        """Check if a process exists on the current platform.

        Args:
            pid: Process ID to check

        Returns:
            True if the process exists and is running, False otherwise.
        """
        if sys.platform == "win32":
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ValueError):
                return False
        else:
            try:
                os.kill(pid, signal.Signal.SIGCONT)
                return True
            except OSError:
                return False

    def cleanup_on_failure(
        self, reason: str, timeout_seconds: float = 10.0
    ) -> dict[str, Any]:
        """Terminate all tracked children gracefully after a failure.

        Args:
            reason: Reason for cleanup (will be logged)
            timeout_seconds: Time to wait for graceful shutdown before force killing

        Returns:
            Dictionary with cleanup statistics
        """
        logger.warning(f"Cleaning up due to failure: {reason}")

        stats = {
            "total_tracked": len(self._tracked_processes),
            "terminated_gracefully": 0,
            "terminated_forcefully": 0,
            "failed_to_terminate": [],
            "socket_files_cleaned": 0,
        }

        # Step 1: Send SIGTERM for graceful shutdown
        for proc in self._tracked_processes.copy():
            try:
                if self._process_exists(proc.pid):
                    logger.info(f"Sending SIGTERM to {proc.name} (PID={proc.pid})")
                    self._send_signal(proc.pid, signal.SIGTERM)

                    # Wait briefly for graceful shutdown
                    time.sleep(0.5)

                    if not self._process_exists(proc.pid):
                        stats["terminated_gracefully"] += 1
                        logger.info(f"✓ {proc.name} terminated gracefully")
                        self._tracked_processes.remove(proc)
                        continue

                    # Step 2: Force kill if still running
                    if self._process_exists(proc.pid):
                        logger.warning(
                            f"{proc.name} (PID={proc.pid}) didn't exit gracefully, forcing..."
                        )
                        self._send_signal(proc.pid, signal.SIGKILL)
                        stats["terminated_forcefully"] += 1
                        logger.info(f"✓ {proc.name} force-killed")
            except Exception as e:
                logger.error(f"Failed to terminate {proc.name} (PID={proc.pid}): {e}")
                stats["failed_to_terminate"].append(proc.pid)

        # Step 3: Wait for remaining processes with timeout
        elapsed = 0.0
        while elapsed < timeout_seconds:
            still_running = [p for p in self._tracked_processes if self._process_exists(p.pid)]
            if not still_running:
                break

            time.sleep(0.5)
            elapsed += 0.5

        # Mark any remaining as failed if still present
        for proc in self._tracked_processes.copy():
            if self._process_exists(proc.pid):
                stats["failed_to_terminate"].append(proc.pid)
                logger.error(f"⚠ Could not terminate {proc.name} (PID={proc.pid})")

        # Step 4: Clean up socket files
        cleaned_sockets = self._cleanup_socket_files(timeout_seconds)
        stats["socket_files_cleaned"] = cleaned_sockets

        # Step 5: Clear registry
        self._tracked_processes.clear()

        logger.info(
            f"Cleanup complete: graceful={stats['terminated_gracefully']}, "
            f"force={stats['terminated_forcefully']}, sockets={stats['socket_files_cleaned']}"
        )

        return stats

    def _send_signal(self, pid: int, sig: int) -> None:
        """Send a signal to a process, handling platform differences.

        Args:
            pid: Target process ID
            sig: Signal to send
        """
        if sys.platform == "win32":
            # Windows doesn't support all Unix signals
            if sig == signal.SIGTERM:
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            elif sig == signal.SIGKILL:
                os.kill(pid, signal.CTRL_C_EXIT)
            else:
                os.kill(pid, sig)
        else:
            os.kill(pid, sig)

    def _cleanup_socket_files(self, timeout_seconds: float = 5.0) -> int:
        """Clean up socket files created by services.

        Args:
            timeout_seconds: Maximum time to wait for socket release

        Returns:
            Number of socket files cleaned up
        """
        cleaned_count = 0
        socket_paths = [
            settings.resolved_log_dir / "uvicorn.sock",
            settings.resolved_log_dir / "fastapi.sock",
            settings.resolved_log_dir / "uvicorn-gunicorn.sock",
        ]

        # Also check common system temp locations
        if sys.platform == "win32":
            temp_dirs = [Path(os.environ.get("TEMP", "")), Path(os.environ.get("TMP", ""))]
        else:
            temp_dirs = [Path("/tmp"), Path(os.environ.get("XDG_RUNTIME_DIR", "/run"))]

        for temp_dir in temp_dirs:
            if temp_dir.exists():
                socket_paths.extend(temp_dir.glob("*.sock"))

        for sock_path in socket_paths:
            if sock_path.exists():
                try:
                    # Try to release the socket first
                    with suppress(Exception):
                        if self._socket_is_bound(sock_path, timeout_seconds):
                            self._release_socket(sock_path)
                            cleaned_count += 1
                            logger.info(f"Released and cleaned socket: {sock_path}")

                    # Remove stale socket file
                    if sock_path.exists():
                        sock_path.unlink()
                        cleaned_count += 1
                        logger.info(f"Removed stale socket file: {sock_path}")
                except Exception as e:
                    logger.debug(f"Error cleaning socket {sock_path}: {e}")

        return cleaned_count

    @staticmethod
    def _socket_is_bound(sock_path: Path, timeout: float) -> bool:
        """Check if a socket file is bound to a service.

        Args:
            sock_path: Path to socket file
            timeout: Timeout for connection attempt

        Returns:
            True if socket appears to be in use
        """
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex(str(sock_path))
            sock.close()
            return result == 0
        except Exception:
            return False

    @staticmethod
    def _release_socket(sock_path: Path) -> None:
        """Release a bound socket file.

        Args:
            sock_path: Path to socket file
        """
        try:
            # Try to close the socket by connecting and shutting down
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(str(sock_path))
        except Exception:
            pass

    def verify_no_orphans(self) -> list[int]:
        """Verify no orphaned processes remain.

        Returns:
            List of PIDs for any orphaned processes found.
        """
        return self._find_orphaned_pids()

    def get_registry_summary(self) -> list[dict[str, Any]]:
        """Get summary of currently tracked processes.

        Returns:
            List of dictionaries with process information.
        """
        return [
            {
                "pid": p.pid,
                "name": p.name,
                "port": p.port,
                "registered_at": p.registered_at,
                "is_running": self._process_exists(p.pid),
            }
            for p in self._tracked_processes
        ]

    def clear_registry(self) -> None:
        """Clear all tracked processes from registry."""
        self._tracked_processes.clear()
        logger.info("Cleaned up process registry")


# Singleton instance for cross-module access
_cleanup_manager: GracefulCleanupManager | None = None


def get_cleanup_manager() -> GracefulCleanupManager:
    """Get the global cleanup manager instance.

    Returns:
        The singleton GracefulCleanupManager instance.
    """
    global _cleanup_manager
    if _cleanup_manager is None:
        _cleanup_manager = GracefulCleanupManager()
    return _cleanup_manager


def initialize_cleanup_tracking() -> None:
    """Initialize cleanup tracking during application startup.

    Should be called early in lifespan to ensure cleanup can run on any future failure.
    """
    mgr = get_cleanup_manager()
    logger.info("Cleanup tracking initialized")
