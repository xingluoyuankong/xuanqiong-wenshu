# AIMETA P=生成日志服务_实时流式记录|R=流式日志推送|NR=不含持久化|E=GenerationLogService|X=internal|A=服务类|D=asyncio|S=none|RD=./README.ai
"""
生成日志服务 - 实时记录和流式输出生成进度

支持多任务并发日志记录，前端可通过 SSE 订阅实时日志。
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """单条日志条目"""
    task_id: str
    level: str  # info, warning, error, success
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class GenerationLogService:
    """
    生成日志服务
    
    特性：
    - 按任务 ID 隔离日志流
    - 支持实时订阅（SSE 友好）
    - 内存环形缓冲区，防止内存泄漏
    - 自动清理过期任务日志
    """

    def __init__(self, max_buffer_per_task: int = 500, max_idle_seconds: int = 3600):
        self._buffers: Dict[str, List[LogEntry]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._max_buffer = max_buffer_per_task
        self._max_idle = max_idle_seconds
        self._last_activity: Dict[str, float] = {}
        self._owners: Dict[str, Optional[int]] = {}
        self._lock = asyncio.Lock()

    def create_task(self, task_id: Optional[str] = None, *, owner_user_id: Optional[int] = None) -> str:
        """创建新日志任务并绑定归属用户，返回 task_id。"""
        tid = task_id or f"task-{uuid.uuid4().hex[:12]}"
        existing_owner = self._owners.get(tid)
        if existing_owner is not None and existing_owner != owner_user_id:
            raise PermissionError("task does not belong to current user")
        self._buffers.setdefault(tid, [])
        self._subscribers.setdefault(tid, [])
        self._last_activity[tid] = time.monotonic()
        self._owners[tid] = owner_user_id
        return tid

    async def ensure_owner(self, task_id: str, owner_user_id: Optional[int]) -> None:
        """校验日志任务归属，不允许读取未知任务时隐式创建。"""
        async with self._lock:
            if task_id not in self._owners:
                raise LookupError("task does not exist")
            if self._owners[task_id] != owner_user_id:
                raise PermissionError("task does not belong to current user")

    async def log(
        self,
        task_id: str,
        message: str,
        level: str = "info",
        metadata: Optional[Dict] = None,
        *,
        owner_user_id: Optional[int] = None,
    ) -> LogEntry:
        """记录一条日志并校验任务归属。"""
        await self.ensure_owner(task_id, owner_user_id)
        entry = LogEntry(
            task_id=task_id,
            level=level,
            message=message,
            metadata=metadata or {},
        )

        async with self._lock:
            if task_id not in self._buffers:
                self._buffers[task_id] = []
                self._subscribers[task_id] = []

            buffer = self._buffers[task_id]
            buffer.append(entry)
            # 环形缓冲区溢出保护
            if len(buffer) > self._max_buffer:
                self._buffers[task_id] = buffer[-self._max_buffer:]

            self._last_activity[task_id] = time.monotonic()

            # 推送给所有订阅者
            dead_queues = []
            for queue in self._subscribers.get(task_id, []):
                try:
                    queue.put_nowait(entry)
                except asyncio.QueueFull:
                    pass
                except Exception:
                    dead_queues.append(queue)

            # 清理失效订阅
            for dq in dead_queues:
                self._subscribers[task_id].remove(dq)

        return entry

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        """订阅某个任务的日志流"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = []
            self._subscribers[task_id].append(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        """取消订阅"""
        async with self._lock:
            if task_id in self._subscribers and queue in self._subscribers[task_id]:
                self._subscribers[task_id].remove(queue)

    async def stream_logs(self, task_id: str, *, owner_user_id: Optional[int] = None) -> AsyncIterator[LogEntry]:
        """SSE 流式生成器：先发历史日志，再实时推送新增。"""
        await self.ensure_owner(task_id, owner_user_id)
        # 先发送历史
        history = await self.get_history(task_id)
        for entry in history:
            yield entry

        # 再实时订阅
        queue = await self.subscribe(task_id)
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield entry
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield LogEntry(
                        task_id=task_id,
                        level="heartbeat",
                        message="",
                        metadata={"type": "keepalive"},
                    )
        except (GeneratorExit, asyncio.CancelledError):
            pass
        finally:
            await self.unsubscribe(task_id, queue)

    async def get_history(self, task_id: str, limit: int = 100) -> List[LogEntry]:
        """获取某个任务的历史日志"""
        buffer = self._buffers.get(task_id, [])
        return buffer[-limit:]

    async def get_all_tasks(self, *, owner_user_id: Optional[int] = None) -> List[Dict]:
        """获取当前用户的活跃任务概要（带超时保护，避免阻塞）。"""
        try:
            async with self._lock:
                tasks = []
                buffers_snapshot = dict(self._buffers)
                for tid, buffer in buffers_snapshot.items():
                    if self._owners.get(tid) != owner_user_id:
                        continue
                    last_entry = buffer[-1] if buffer else None
                    tasks.append({
                        "task_id": tid,
                        "log_count": len(buffer),
                        "last_activity": datetime.fromtimestamp(
                            self._last_activity.get(tid, 0), tz=timezone.utc
                        ).isoformat(),
                        "latest_level": last_entry.level if last_entry else None,
                        "subscriber_count": len(self._subscribers.get(tid, [])),
                    })
                return tasks
        except Exception:
            return []

    async def complete_task(self, task_id: str, *, owner_user_id: Optional[int] = None) -> None:
        """标记任务完成，通知订阅者结束。"""
        await self.log(task_id, "任务完成", level="success", metadata={"type": "complete"}, owner_user_id=owner_user_id)

    async def cleanup_expired(self) -> int:
        """清理过期任务日志，返回清理数量"""
        now = time.monotonic()
        expired = [
            tid for tid, last in self._last_activity.items()
            if now - last > self._max_idle
        ]
        async with self._lock:
            for tid in expired:
                self._buffers.pop(tid, None)
                self._subscribers.pop(tid, None)
                self._last_activity.pop(tid, None)
                self._owners.pop(tid, None)
                self._owners.pop(tid, None)
        return len(expired)


# 全局单例
_generation_log_service: Optional[GenerationLogService] = None


def get_generation_log_service() -> GenerationLogService:
    """获取全局日志服务单例"""
    global _generation_log_service
    if _generation_log_service is None:
        _generation_log_service = GenerationLogService()
    return _generation_log_service
