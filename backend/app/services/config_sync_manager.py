# AIMETA P=配置同步器_缓存失效通知|R=缓存失效事件|NR=不含业务逻辑|E=ConfigSyncManager|X=internal|A=事件管理器|D=asyncio|S=none|RD=./README.ai
"""
配置同步管理器

确保前端修改配置后，后端所有服务能立即感知并更新。
通过事件总线机制通知所有订阅者配置变更。
"""
import asyncio
import logging
import time
from typing import Callable, Dict, List, Set

logger = logging.getLogger(__name__)


class ConfigSyncManager:
    """
    配置变更同步管理器
    
    功能：
    - 记录每个用户的配置版本号
    - 配置变更时递增版本号并通知所有订阅者
    - 支持跨服务/跨会话配置同步
    """

    def __init__(self):
        self._user_versions: Dict[int, int] = {}
        self._subscribers: Dict[int, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._last_change: Dict[int, float] = {}

    async def bump_version(self, user_id: int) -> int:
        """
        递增用户的配置版本号，通知所有订阅者
        在配置写入成功后调用
        """
        async with self._lock:
            current = self._user_versions.get(user_id, 0)
            new_version = current + 1
            self._user_versions[user_id] = new_version
            self._last_change[user_id] = time.monotonic()

            # 通知所有订阅者
            dead_queues = []
            for queue in self._subscribers.get(user_id, []):
                try:
                    queue.put_nowait({
                        "user_id": user_id,
                        "version": new_version,
                        "timestamp": time.monotonic(),
                    })
                except asyncio.QueueFull:
                    pass
                except Exception:
                    dead_queues.append(queue)

            for dq in dead_queues:
                self._subscribers[user_id].remove(dq)

            logger.info("用户 %s 的配置版本更新为 v%s", user_id, new_version)
            return new_version

    async def get_version(self, user_id: int) -> int:
        """获取用户当前配置版本号"""
        return self._user_versions.get(user_id, 0)

    async def subscribe(self, user_id: str) -> asyncio.Queue:
        """订阅某个用户的配置变更事件"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        async with self._lock:
            if user_id not in self._subscribers:
                self._subscribers[user_id] = []
            self._subscribers[user_id].append(queue)
        return queue

    async def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        """取消订阅"""
        async with self._lock:
            if user_id in self._subscribers and queue in self._subscribers[user_id]:
                self._subscribers[user_id].remove(queue)

    async def invalidate_user_cache(self, user_id: int) -> Dict:
        """
        使指定用户的缓存失效
        返回失效详情，供日志记录
        """
        async with self._lock:
            old_version = self._user_versions.get(user_id, 0)
            new_version = old_version + 1
            self._user_versions[user_id] = new_version
            self._last_change[user_id] = time.monotonic()

            subscriber_count = len(self._subscribers.get(user_id, []))

            logger.info(
                "用户 %s 的缓存已失效：v%s -> v%s (订阅者: %s)",
                user_id, old_version, new_version, subscriber_count,
            )

            return {
                "user_id": user_id,
                "previous_version": old_version,
                "current_version": new_version,
                "subscriber_count": subscriber_count,
                "timestamp": self._last_change[user_id],
            }

    async def get_all_versions(self) -> Dict[int, int]:
        """获取所有用户的当前版本号"""
        return dict(self._user_versions)


# 全局单例
_config_sync_manager: ConfigSyncManager | None = None


def get_config_sync_manager() -> ConfigSyncManager:
    """获取全局配置同步管理器单例"""
    global _config_sync_manager
    if _config_sync_manager is None:
        _config_sync_manager = ConfigSyncManager()
    return _config_sync_manager
