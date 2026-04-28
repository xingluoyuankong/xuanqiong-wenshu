# AIMETA P=使用统计服务_API调用统计|R=统计记录_限额检查|NR=不含数据访问|E=UsageService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import AsyncSessionLocal
from ..models import UsageMetric

logger = logging.getLogger(__name__)
_LOCK_RETRY_KEYWORDS = (
    "database is locked",
    "database table is locked",
    "lock wait timeout",
    "deadlock found",
    "deadlock detected",
)


class UsageService:
    """通用计数服务，目前用于统计 API 请求次数等。"""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    @staticmethod
    def _is_retryable_write_error(exc: OperationalError) -> bool:
        message = str(getattr(exc, "orig", exc) or exc).lower()
        return any(keyword in message for keyword in _LOCK_RETRY_KEYWORDS)

    async def increment(self, key: str, *, max_retries: int = 3) -> None:
        """使用独立短事务增加计数器，避免污染主业务会话。"""
        last_error: Exception | None = None
        for attempt in range(max_retries):
            async with AsyncSessionLocal() as session:
                try:
                    result = await session.execute(
                        update(UsageMetric)
                        .where(UsageMetric.key == key)
                        .values(value=UsageMetric.value + 1)
                    )
                    if result.rowcount == 0:
                        session.add(UsageMetric(key=key, value=1))
                    await session.commit()
                    return
                except IntegrityError as exc:
                    last_error = exc
                    await session.rollback()
                except OperationalError as exc:
                    last_error = exc
                    await session.rollback()
                    if not self._is_retryable_write_error(exc):
                        raise
            if attempt < max_retries - 1:
                await asyncio.sleep(0.05 * (attempt + 1))

        if last_error is not None:
            raise last_error

    async def get_value(self, key: str) -> int:
        if self.session is not None:
            return await self._get_value_with_session(self.session, key)

        async with AsyncSessionLocal() as session:
            return await self._get_value_with_session(session, key)

    @staticmethod
    async def _get_value_with_session(session: AsyncSession, key: str) -> int:
        result = await session.execute(select(UsageMetric.value).where(UsageMetric.key == key))
        value = result.scalar_one_or_none()
        return int(value or 0)
