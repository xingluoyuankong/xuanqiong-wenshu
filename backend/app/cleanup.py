"""
Cleanup utilities for orphaned processes and socket files.
Cross-platform support for Windows/Linux/macOS.
"""

import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def find_process_by_port(port: int, timeout: float = 1.0) -> Optional[int]:
    """Find PID of process listening on the given port."""
    try:
        # Try to bind to port - if fails, something is using it
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        
        # Check if port is in use
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            logger.warning(f"Port {port} is already in use")
            
            # Cross-platform: use different methods based on OS
            if sys.platform == 'win32':
                return _find_pid_windows(port)
            else:
                return _find_pid_unix(port)
    except Exception as e:
        logger.error(f"Failed to check port {port}: {e}")
    
    return None


def _find_pid_windows(port: int) -> Optional[int]:
    """Windows-specific: get PID from netstat or Get-NetTCPConnection."""
    try:
        # Try PowerShell method first (more reliable)
        cmd = [
            'powershell', '-Command',
            f'Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | '
            f'Select-Object -ExpandProperty OwningProcess'
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5
        )
        pid_str = result.stdout.strip()
        if pid_str.isdigit():
            return int(pid_str)
    except Exception:
        pass
    
    # Fallback: parse netstat output
    try:
        cmd = ['netstat', '-ano']
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    return int(parts[-1])
    except Exception:
        pass
    
    return None


def _find_pid_unix(port: int) -> Optional[int]:
    """Unix-specific: use lsof or ss/netstat."""
    # Try lsof first
    try:
        cmd = ['lsof', '-i', f':{port}', '-t']
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().split('\n')[0])
    except Exception:
        pass
    
    # Fallback: ss or netstat
    try:
        for cmd_name in ['ss', 'netstat']:
            try:
                cmd = [cmd_name, '-tnlp'] if cmd_name == 'ss' else ['-an']
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if f':{port}' in line and ('LISTEN' in line or ':%d' % port in line):
                        # Extract PID from output
                        parts = line.split()
                        for part in parts:
                            if part.isdigit():
                                return int(part)
            except FileNotFoundError:
                continue
    except Exception:
        pass
    
    return None


def _proc_state(pid: int) -> Optional[str]:
    """Read the process state char from /proc (e.g. 'R', 'S', 'Z')."""
    try:
        with open(f'/proc/{pid}/stat', 'r') as fh:
            data = fh.read()
        # comm may contain spaces/parens; state follows the last ')'
        return data.rsplit(')', 1)[1].split()[0]
    except Exception:
        return None


def _process_alive(pid: int) -> bool:
    """Return True if a process with the given PID is alive and not a zombie."""
    # A zombie has already exited; only its exit record remains.
    if _proc_state(pid) == 'Z':
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but owned by another user — still alive.
        return True
    except Exception:
        return False


def _scan_orphans_unix(repo_path_lower: str, markers: tuple, exclude_pids=None) -> list:
    """
    Scan /proc for orphaned repo/service processes on Unix.

    A process is reported when its cmdline references the repo path OR one
    of the service markers (uvicorn / http.server / vite / xuanqiong-wenshu).
    This process, its parent, and any explicitly excluded PIDs (e.g. live
    production services) are skipped.
    """
    orphans = []
    exclude = set(exclude_pids or ())
    exclude.add(os.getpid())
    exclude.add(os.getppid())

    try:
        entries = os.listdir('/proc')
    except Exception as e:
        logger.debug(f"Could not list /proc: {e}")
        return orphans

    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in exclude:
            continue
        try:
            with open(f'/proc/{pid}/cmdline', 'rb') as fh:
                raw = fh.read()
            if not raw:
                continue
            cmdline = raw.replace(b'\x00', b' ').decode('utf-8', 'replace').strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        except Exception:
            continue

        lowered = cmdline.lower()
        hit_repo = bool(repo_path_lower) and repo_path_lower in lowered
        hit_marker = any(marker in lowered for marker in markers)
        if not (hit_repo or hit_marker):
            continue

        orphans.append({'pid': pid, 'command': cmdline})

    return orphans


def stop_process(pid: int, force: bool = True) -> bool:
    """Stop a process by PID.

    Returns True when the process was stopped OR was already gone
    (idempotent success). Returns False only on a genuine failure to
    stop a process that is still alive.
    """
    # Already reaped / never existed: idempotent success, not an error.
    if not _process_alive(pid):
        logger.info(f"✓ Process PID={pid} already exited (no action needed)")
        return True

    try:
        if sys.platform == 'win32':
            # Windows: Stop-Process equivalent
            subprocess.run(
                ['taskkill', '/PID', str(pid), '/F'],
                capture_output=True,
                timeout=5
            )
        else:
            # Unix: kill equivalent
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
            try:
                os.waitpid(pid, 0 if not force else os.WNOHANG)
            except ChildProcessError:
                pass

        # Give the kernel a moment to reap the process before declaring failure.
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not _process_alive(pid):
                logger.info(f"✓ Stopped process PID={pid}")
                return True
            time.sleep(0.1)

        if _process_alive(pid):
            # A zombie (already exited, record not yet reaped) is not a
            # genuine stop failure — treat as success.
            if _proc_state(pid) == 'Z':
                logger.info(f"✓ PID={pid} is a zombie (already exited)")
                return True
            logger.warning(f"✗ PID={pid} still alive after stop attempt")
            return False

        logger.info(f"✓ Stopped process PID={pid}")
        return True
    except Exception as e:
        logger.warning(f"✗ Failed to stop PID={pid}: {e}")
        return False


def cleanup_socket_files(run_dir: Path, patterns: list[str] = None) -> list[str]:
    """Clean up socket files in the run directory."""
    cleaned = []
    
    if patterns is None:
        patterns = ['*.sock', '*.socket', 'uvicorn.sock', 'fastapi.sock']
    
    try:
        for pattern in patterns:
            for sock_file in run_dir.glob(pattern):
                try:
                    if sock_file.is_file():
                        sock_file.unlink()
                        cleaned.append(str(sock_file))
                        logger.info(f"✓ Cleaned up socket file: {sock_file.name}")
                except Exception as e:
                    logger.warning(f"⚠ Could not remove {sock_file}: {e}")
    except Exception as e:
        logger.error(f"Failed to clean socket files: {e}")
    
    return cleaned


def verify_no_zombie_processes(repo_path: str, ports: list[int] = None) -> dict:
    """Verify no zombie/leaked processes remain."""
    result = {
        'orphan_python': [],
        'orphan_node': [],
        'ports_in_use': {},
        'zombie_count': 0
    }
    
    repo_path_lower = repo_path.lower()
    
    PYTHON_MARKERS = ('uvicorn', 'xuanqiong-wenshu', 'http.server')
    NODE_MARKERS = ('vite', 'http.server', 'npm', 'xuanqiong-wenshu')
    try:
        # Never report (or later kill) the live production services.
        prod_pids = set()
        for _p in (8013, 5174):
            _pid = find_process_by_port(_p, timeout=0.3)
            if _pid:
                prod_pids.add(_pid)
        # The http.server/vite front-end is usually spawned by a parent
        # (npm/node supervisor); exclude direct ancestors of prod PIDs too.
        for _pid in list(prod_pids):
            try:
                with open(f'/proc/{_pid}/stat', 'r') as fh:
                    prod_pids.add(int(fh.read().rsplit(')', 1)[1].split()[1]))
            except Exception:
                pass

        if sys.platform == 'win32':
            # Windows: tasklist-based scan (unchanged behaviour)
            for exe in ['python.exe']:
                try:
                    cmd = ['tasklist', '/FI', f'Image eq {exe}.exe']
                    proc_result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=10
                    )
                    for line in proc_result.stdout.splitlines()[1:]:
                        if exe in line.lower():
                            parts = line.split()
                            try:
                                pid = int(parts[1])
                            except (IndexError, ValueError):
                                continue
                            if repo_path_lower in line.lower():
                                result['orphan_python'].append({
                                    'pid': pid,
                                    'command': line.strip()
                                })
                except Exception as e:
                    logger.debug(f"Could not check python processes: {e}")
        else:
            # Unix: real /proc cmdline scan — no longer a no-op.
            result['orphan_python'] = _scan_orphans_unix(
                repo_path_lower, PYTHON_MARKERS, exclude_pids=prod_pids
            )
            result['orphan_node'] = _scan_orphans_unix(
                repo_path_lower, NODE_MARKERS, exclude_pids=prod_pids
            )
    except Exception as e:
        logger.error(f"Failed to verify zombie processes: {e}")
    
    # Check if ports are still in use
    if ports:
        for port in ports:
            if find_process_by_port(port, timeout=0.5):
                result['ports_in_use'][port] = True
    
    result['zombie_count'] = (
        len(result['orphan_python'])
        + len(result['orphan_node'])
        + len(result['ports_in_use'])
    )
    return result


def perform_graceful_cleanup(
    backend_pid: Optional[int],
    frontend_pid: Optional[int],
    repo_path: str,
    run_dir: str,
    ports: list[int] = None,
    process_monitor=None
) -> dict:
    """
    Perform comprehensive cleanup of processes after startup failure.
    
    Args:
        backend_pid: PID of the backend uvicorn process
        frontend_pid: PID of the frontend node/http.server process
        repo_path: Path to the repository root
        run_dir: Runtime log directory for manifest writing
        ports: List of ports to check (default: [8013, 5174])
        process_monitor: Optional ProcessMonitor instance
    
    Returns cleanup report with detailed status.
    """
    result = {
        'backend_stopped': False,
        'frontend_stopped': False,
        'sockets_cleaned': [],
        'remaining_orphans': [],
        'ports_free': True,
        'errors': []
    }
    
    # Set up paths
    repo_path_obj = Path(repo_path)
    run_dir_obj = Path(run_dir) if run_dir else (repo_path_obj / 'logs')
    if not run_dir_obj.is_dir():
        run_dir_obj.mkdir(parents=True, exist_ok=True)
    
    # Track and stop specified PIDs using ProcessMonitor (US-003)
    if process_monitor is not None:
        logger.info("🔍 Recording termination events via ProcessMonitor")
    
    # Stop backend process
    if backend_pid:
        if process_monitor is not None:
            process_monitor.on_child_terminate(
                terminated_pid=backend_pid,
                exit_code=0,
                reason="cleanup_requested"
            )
        if stop_process(backend_pid):
            result['backend_stopped'] = True
        else:
            result['errors'].append(f"Failed to stop backend PID={backend_pid}")
            if process_monitor is not None:
                process_monitor.update_status(backend_pid, "error")
    
    # Stop frontend process
    if frontend_pid:
        if process_monitor is not None:
            process_monitor.on_child_terminate(
                terminated_pid=frontend_pid,
                exit_code=0,
                reason="cleanup_requested"
            )
        if stop_process(frontend_pid):
            result['frontend_stopped'] = True
        else:
            result['errors'].append(f"Failed to stop frontend PID={frontend_pid}")
            if process_monitor is not None:
                process_monitor.update_status(frontend_pid, "error")
    
    # Define ports to check
    if ports is None:
        ports = [8013, 5174]
    
    # Cleanup socket files
    try:
        result['sockets_cleaned'] = cleanup_socket_files(run_dir_obj)
    except Exception as e:
        result['errors'].append(f"Socket cleanup failed: {e}")
    
    # Force stop any remaining processes on our ports
    for port in ports:
        pid = find_process_by_port(port)
        if pid:
            logger.info(f"Forcing stop of PID={pid} on port {port}")
            if process_monitor is not None:
                process_monitor.on_child_terminate(
                    terminated_pid=pid,
                    exit_code=-1,
                    reason=f"force_stop_port_{port}"
                )
            stop_process(pid, force=True)
            result['ports_free'] = True
    
    # Verify no zombies remain
    verification = verify_no_zombie_processes(repo_path, ports)
    
    result['remaining_orphans'] = (
        list(verification.get('orphan_python', []))
        + list(verification.get('orphan_node', []))
    )
    result['ports_free'] = len(verification.get('ports_in_use', {})) == 0
    
    # Finalize monitoring session and write manifest (US-003)
    if process_monitor is not None:
        logger.info("💾 Finalizing process manifest")
        process_monitor.finalize()
    
    return result
