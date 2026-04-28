# AIMETA P=数据库会话_异步会话工厂|R=异步会话_连接池|NR=不含查询逻辑|E=AsyncSessionLocal_get_db|X=internal|A=会话工厂|D=sqlalchemy|S=db|RD=./README.ai
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..core.config import settings

# 根据不同数据库驱动调整连接池参数，确保在多数据库环境下表现稳定
engine_kwargs = {"echo": settings.sqlalchemy_echo}
if settings.is_sqlite_backend:
    # SQLite 场景下禁用连接池并放宽线程检查，避免多协程读写冲突
    # 启用 WAL 模式支持并发读写，增加超时避免锁定
    engine_kwargs.update(
        pool_pre_ping=False,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,  # 等待锁释放的超时时间（秒）
        },
        poolclass=NullPool,
    )
else:
    # MySQL 场景保持健康检查与连接复用，并为后台任务并发写提供稳定连接池
    engine_kwargs.update(
        pool_pre_ping=True,
        pool_size=settings.mysql_pool_size,
        max_overflow=settings.mysql_max_overflow,
        pool_timeout=settings.mysql_pool_timeout,
        pool_recycle=settings.mysql_pool_recycle,
        pool_use_lifo=settings.mysql_pool_use_lifo,
    )

engine = create_async_engine(settings.sqlalchemy_database_uri, **engine_kwargs)

# SQLite 启用 WAL 模式，支持并发读写
if settings.is_sqlite_backend:

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30秒超时
        cursor.close()

# 统一的 Session 工厂，禁用 expire_on_commit 方便返回模型对象
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖项：提供一个作用域内共享的数据库会话。"""
    async with AsyncSessionLocal() as session:
        yield session
