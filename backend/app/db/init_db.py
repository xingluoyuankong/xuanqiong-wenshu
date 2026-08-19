# AIMETA P=数据库初始化_创建表和默认数据|R=创建表_初始化管理员|NR=不含业务逻辑|E=init_db|X=internal|A=初始化函数|D=sqlalchemy|S=db|RD=./README.ai
import asyncio
import logging
import os
import threading
from contextlib import contextmanager

from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ..core.config import settings
from ..core.security import hash_password
from ..models import Prompt, SystemConfig, User
from .system_config_defaults import SYSTEM_CONFIG_DEFAULTS
from .session import AsyncSessionLocal

logger = logging.getLogger(__name__)


_MIGRATION_THREAD_LOCK = threading.Lock()


def _migration_lock_path() -> Path:
    """Return a stable lock file next to the configured database.

    The lock is deliberately outside SQLite so two fresh workers cannot both
    run ``create_all`` from the baseline migration at the same time.  The file
    itself is harmless and may remain after an unclean process exit.
    """
    url = make_url(settings.sqlalchemy_database_uri)
    database = Path(url.database or "app")
    if not database.is_absolute():
        database = (Path(__file__).resolve().parents[2] / database).resolve()
    return database.parent / f".{database.name}.migration.lock"


@contextmanager
def _migration_lock():
    """Serialize migrations within and across processes.

    ``msvcrt.locking`` is used on Windows; ``fcntl.flock`` is used on POSIX.
    Both locks are released automatically when the context exits, including on
    exceptions.  A process-local lock avoids the Windows limitation that a
    process can otherwise reacquire its own file lock.
    """
    lock_path = _migration_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _MIGRATION_THREAD_LOCK:
        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                lock_file.write(b"0")
                lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - exercised on Linux CI/deployments
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


async def init_db() -> None:
    """初始化数据库结构并确保默认管理员存在。"""

    await _ensure_database_exists()

    # ---- 第一步：只通过版本化迁移建立/升级结构 ----
    await _run_schema_migrations()
    logger.info("数据库迁移已升级到最新版本")

    # ---- 第二步：确保管理员账号至少存在一个 ----
    async with AsyncSessionLocal() as session:
        admin_exists = await session.execute(select(User).where(User.is_admin.is_(True)))
        if not admin_exists.scalars().first():
            logger.warning("未检测到管理员账号，正在创建默认管理员 ...")
            admin_user = User(
                username=settings.admin_default_username,
                email=settings.admin_default_email,
                hashed_password=hash_password(settings.admin_default_password),
                is_admin=True,
            )

            session.add(admin_user)
            try:
                await session.commit()
                logger.info("默认管理员创建完成：%s", settings.admin_default_username)
            except IntegrityError:
                await session.rollback()
                logger.exception("默认管理员创建失败，可能是并发启动导致，请检查数据库状态")

        # ---- 第三步：同步系统配置到数据库 ----
        # 不能只做“先查后插”：多个应用进程同时启动时，两边都可能查不到
        # 同一默认项，随后由唯一键约束把整个初始化事务打断。每一项使用
        # 独立保存点，冲突只回滚当前项并读取已经提交的胜者。
        for entry in SYSTEM_CONFIG_DEFAULTS:
            value = entry.value_getter(settings)
            if value is None:
                continue
            existing = await session.get(SystemConfig, entry.key)
            if existing:
                if entry.description and existing.description != entry.description:
                    existing.description = entry.description
                continue
            try:
                savepoint = await session.begin_nested()
                session.add(
                    SystemConfig(
                        key=entry.key,
                        value=value,
                        description=entry.description,
                    )
                )
                await session.flush()
                await savepoint.commit()
            except IntegrityError:
                await savepoint.rollback()
                existing = await session.get(SystemConfig, entry.key)
                if existing and entry.description and existing.description != entry.description:
                    existing.description = entry.description
                elif existing is None:
                    raise

        await _ensure_default_prompts(session)

        await session.commit()


async def _run_schema_migrations() -> None:
    """Run Alembic in a worker thread so the async app loop remains healthy."""
    from alembic import command
    from alembic.config import Config

    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    if not alembic_ini.is_file():
        raise RuntimeError(f"Alembic configuration not found: {alembic_ini}")

    def _upgrade() -> None:
        config = Config(str(alembic_ini))
        command.upgrade(config, "head")

    # The lock must cover the complete Alembic run, not just engine creation:
    # the baseline migration creates every table and is not safe to race.
    await asyncio.to_thread(lambda: _run_locked_upgrade(_upgrade))


def _run_locked_upgrade(upgrade) -> None:
    with _migration_lock():
        upgrade()


async def _ensure_database_exists() -> None:
    """在首次连接前确认数据库存在，针对不同驱动做最小化准备工作。"""
    url = make_url(settings.sqlalchemy_database_uri)
    backend_name = url.get_backend_name()

    if backend_name == "sqlite":
        # SQLite 采用文件数据库，确保父目录存在即可，无需额外建库语句
        db_path = Path(url.database or "").expanduser()
        if not db_path.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            db_path = (project_root / db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return

    if backend_name != "mysql":
        logger.warning("当前数据库后端 %s 不支持自动建库，跳过 CREATE DATABASE 阶段", backend_name)
        return

    database = (url.database or "").strip("/")
    if not database:
        return

    admin_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=None,
        query=url.query,
    )

    admin_engine = create_async_engine(
        admin_url.render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database}`"))
    finally:
        await admin_engine.dispose()


async def _ensure_default_prompts(session: AsyncSession) -> None:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    if not prompts_dir.is_dir():
        return

    result = await session.execute(select(Prompt.name))
    existing_names = set(result.scalars().all())

    for prompt_file in sorted(prompts_dir.glob("*.md")):
        name = prompt_file.stem
        if name in existing_names:
            continue
        content = prompt_file.read_text(encoding="utf-8")
        try:
            savepoint = await session.begin_nested()
            session.add(Prompt(name=name, content=content))
            await session.flush()
            await savepoint.commit()
            existing_names.add(name)
        except IntegrityError:
            await savepoint.rollback()
            existing_names.add(name)
