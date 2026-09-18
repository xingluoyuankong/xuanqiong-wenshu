"""进程管理模块 - 用于追踪子进程并生成运行时 manifest."""
import json
import logging
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class ProcessManifest:
    """运行时进程信息记录器.

    Attributes:
        parent_pid: 父进程 ID (当前应用)
        children: 子进程列表，每个包含 PID、命令、启动时间等
        timestamp: Manifest 创建时间戳
    """

    def __init__(self) -> None:
        self.parent_pid = os.getpid()
        self.children: list[dict[str, Any]] = []
        self.timestamp = datetime.utcnow().isoformat()

    def add_child(
        self,
        pid: int,
        command: str,
        args: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """添加子进程到 manifest.

        Args:
            pid: 子进程 PID
            command: 执行的命令路径
            args: 命令行参数列表
            kwargs: 传递给 subprocess.Popen 的其他参数
        """
        cmd_str = " ".join([command] + (args or []))
        start_time = datetime.utcnow().isoformat()

        self.children.append(
            {
                "pid": pid,
                "command": cmd_str,
                "start_time": start_time,
                "exit_code": None,
                "reason": "",
                "ended_at": None,
                "handle_kwargs": kwargs,
            }
        )
        logger.info("子进程已启动｜PID=%d 命令=%s", pid, cmd_str)

    def record_exit(self, pid: int, exit_code: int, reason: str) -> None:
        """记录子进程退出信息.

        Args:
            pid: 子进程 PID
            exit_code: 退出码 (0=成功，非 0=失败)
            reason: 退出于因说明
        """
        for child in self.children:
            if child["pid"] == pid:
                child["exit_code"] = exit_code
                child["reason"] = reason
                child["ended_at"] = datetime.utcnow().isoformat()
                logger.info(
                    "子进程已退出｜PID=%d 退出码=%d 原因=%s",
                    pid,
                    exit_code,
                    reason,
                )
                break

    def to_json(self) -> str:
        """将 manifest 转换为 JSON 字符串.

        输出同时包含 ``start_time``/``ended_at`` 等原生字段，
        以及约定的 ``cmd``/``exit_reason`` 别名，便于排障脚本统一读取。

        Returns:
            JSON 格式的 manifest 字符串（不含 handle_kwargs）
        """
        output = {
            "parent_pid": self.parent_pid,
            "children": [
                {
                    k: v for k, v in {**c, "cmd": c.get("command"), "exit_reason": c.get("reason")}.items()
                    if k != "handle_kwargs"
                }
                for c in self.children
            ],
            "timestamp": self.timestamp,
        }
        return json.dumps(output, ensure_ascii=False, indent=2)

    def write_to_file(self) -> Path:
        """将 manifest 写入 runtime_log_dir/current_run.json.

        Returns:
            写入的文件路径
        """
        runtime_dir = settings.runtime_log_dir
        runtime_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = runtime_dir / "current_run.json"
        content = self.to_json()
        manifest_path.write_text(content, encoding="utf-8")

        logger.info("Process manifest 已写入 %s", manifest_path)
        return manifest_path


# 全局单例实例
_manifest_instance: Optional[ProcessManifest] = None


def get_manifest() -> ProcessManifest:
    """获取或创建唯一的 ProcessManifest 实例.

    Returns:
        全局单例实例
    """
    global _manifest_instance
    if _manifest_instance is None:
        _manifest_instance = ProcessManifest()
    return _manifest_instance


def save_manifest() -> Path:
    """保存当前 manifest 到文件.

    Returns:
        文件路径

    Raises:
        RuntimeError: 如果没有初始化 manifest
    """
    if _manifest_instance is None:
        raise RuntimeError("Process manager 未初始化")
    return _manifest_instance.write_to_file()


# ---- US-003 清晰 API 别名（复用上面既有单例，不另造一套） ----


def write_child_manifest(
    pid: int,
    command: str,
    args: list[str] | None = None,
    **kwargs: Any,
) -> None:
    """记录一个子进程启动事件（PID、命令、启动时间、父子关系）.

    这是 :meth:`ProcessManifest.add_child` 的顶层便捷 API，
    供 start 流程直接调用。

    Args:
        pid: 子进程 PID
        command: 执行的命令路径
        args: 命令行参数列表
        kwargs: 传递给 subprocess.Popen 的其他参数
    """
    get_manifest().add_child(pid=pid, command=command, args=args, **kwargs)


def record_child_exit(pid: int, exit_code: int, reason: str) -> None:
    """记录子进程终止事件（退出码、退出原因、结束时间）.

    这是 :meth:`ProcessManifest.record_exit` 的顶层便捷 API。

    Args:
        pid: 子进程 PID
        exit_code: 退出码 (0=成功，非 0=失败)
        reason: 退出原因说明
    """
    get_manifest().record_exit(pid=pid, exit_code=exit_code, reason=reason)


def cleanup_orphan_children(pids: set[int]) -> None:
    """清理遗留的子进程.

    Args:
        pids: 需要终止的进程 ID 集合
    """
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            logger.warning("已发送 SIGTERM 给孤儿进程｜PID=%d", pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            logger.error("无法终止进程｜PID=%d", pid)


# 用于跟踪所有创建的 Popen 对象
_all_processes: set[subprocess.Popen[Any]] = set()


def track_process(process: subprocess.Popen[Any]) -> None:
    """追踪一个子进程以便后续回收.

    Args:
        process: subprocess.Popen 对象
    """
    _all_processes.add(process)
    manifest = get_manifest()
    manifest.add_child(
        pid=process.pid,
        command=process.args[0] if isinstance(process.args, list) else process.args,
        args=process.args if isinstance(process.args, list) else [],
    )


def untrack_process(process: subprocess.Popen[Any]) -> None:
    """从追踪中移除进程.

    Args:
        process: subprocess.Popen 对象
    """
    _all_processes.discard(process)


def get_all_pids() -> set[int]:
    """获取所有被追踪的进程 PID.

    Returns:
        进程 ID 集合
    """
    return {p.pid for p in _all_processes if p.poll() is None}


def terminate_all_processes() -> None:
    """终止所有被追踪的活跃子进程.

    调用前应先尝试 graceful shutdown (SIGTERM),
    如果超时则强制 kill (SIGKILL).
    """
    active_pids = set()
    for proc in _all_processes.copy():
        if proc.poll() is None:  # 还在运行
            try:
                proc.terminate()
                active_pids.add(proc.pid)
            except Exception as e:
                logger.error("终止进程失败｜PID=%d 错误=%s", proc.pid, e)

    # 等待优雅终止
    for proc in _all_processes.copy():
        if proc.poll() is None:
            try:
                proc.wait(timeout=5)  # 5 秒后强制终止
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    logger.warning("强制杀死超时进程｜PID=%d", proc.pid)
                except Exception as e:
                    logger.error("强制杀死进程失败｜PID=%d 错误=%s", proc.pid, e)
            finally:
                untrack_process(proc)

    _all_processes.clear()
    logger.info("所有子进程已终止")
