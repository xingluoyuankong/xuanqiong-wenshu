# AIMETA P=数据库初始化_创建表和默认数据|R=创建表_初始化管理员|NR=不含业务逻辑|E=init_db|X=internal|A=初始化函数|D=sqlalchemy|S=db|RD=./README.ai
import logging

from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ..core.config import settings
from ..core.security import hash_password
from ..models import Prompt, SystemConfig, User
from .base import Base
from .system_config_defaults import SYSTEM_CONFIG_DEFAULTS
from .session import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """初始化数据库结构并确保默认管理员存在。"""

    await _ensure_database_exists()

    # ---- 第一步：创建所有表结构 ----
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构已初始化")
    await _ensure_schema_updates()

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
        for entry in SYSTEM_CONFIG_DEFAULTS:
            value = entry.value_getter(settings)
            if value is None:
                continue
            existing = await session.get(SystemConfig, entry.key)
            if existing:
                if entry.description and existing.description != entry.description:
                    existing.description = entry.description
                continue
            session.add(
                SystemConfig(
                    key=entry.key,
                    value=value,
                    description=entry.description,
                )
            )

        await _ensure_default_prompts(session)

        await session.commit()


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


async def _ensure_schema_updates() -> None:
    """补齐历史版本缺失的列，避免旧库在新版本报错。"""
    async with engine.begin() as conn:
        def _upgrade(sync_conn):
            inspector = inspect(sync_conn)

            def _has_named_unique(table_name: str, name: str) -> bool:
                indexes = inspector.get_indexes(table_name)
                if any(index.get("name") == name for index in indexes):
                    return True
                unique_constraints = inspector.get_unique_constraints(table_name)
                return any(item.get("name") == name for item in unique_constraints)

            def _has_duplicate_project_chapter_rows(table_name: str) -> bool:
                duplicate = sync_conn.execute(
                    text(
                        f"SELECT project_id, chapter_number, COUNT(*) AS cnt "
                        f"FROM {table_name} GROUP BY project_id, chapter_number HAVING COUNT(*) > 1 LIMIT 1"
                    )
                ).first()
                if duplicate:
                    logger.warning("检测到 %s 存在重复 project_id + chapter_number 记录，跳过唯一索引创建", table_name)
                    return True
                return False

            if inspector.has_table("chapter_outlines"):
                chapter_outline_columns = {col["name"] for col in inspector.get_columns("chapter_outlines")}
                if "metadata" not in chapter_outline_columns:
                    sync_conn.execute(text("ALTER TABLE chapter_outlines ADD COLUMN metadata JSON"))
                if (
                    not _has_named_unique("chapter_outlines", "uq_chapter_outlines_project_chapter_number")
                    and not _has_duplicate_project_chapter_rows("chapter_outlines")
                ):
                    sync_conn.execute(
                        text(
                            "CREATE UNIQUE INDEX uq_chapter_outlines_project_chapter_number "
                            "ON chapter_outlines (project_id, chapter_number)"
                        )
                    )

            if inspector.has_table("chapters"):
                if (
                    not _has_named_unique("chapters", "uq_chapters_project_chapter_number")
                    and not _has_duplicate_project_chapter_rows("chapters")
                ):
                    sync_conn.execute(
                        text(
                            "CREATE UNIQUE INDEX uq_chapters_project_chapter_number "
                            "ON chapters (project_id, chapter_number)"
                        )
                    )

            if inspector.has_table("llm_configs"):
                llm_config_columns = {col["name"] for col in inspector.get_columns("llm_configs")}
                if "llm_provider_profiles" not in llm_config_columns:
                    sync_conn.execute(text("ALTER TABLE llm_configs ADD COLUMN llm_provider_profiles TEXT"))

            if inspector.has_table("user_style_libraries"):
                style_library_columns = {col["name"] for col in inspector.get_columns("user_style_libraries")}
                if "style_sources_json" not in style_library_columns:
                    sync_conn.execute(text("ALTER TABLE user_style_libraries ADD COLUMN style_sources_json TEXT"))
                if "style_profiles_json" not in style_library_columns:
                    sync_conn.execute(text("ALTER TABLE user_style_libraries ADD COLUMN style_profiles_json TEXT"))
                if "global_active_profile_id" not in style_library_columns:
                    sync_conn.execute(text("ALTER TABLE user_style_libraries ADD COLUMN global_active_profile_id TEXT"))
        await conn.run_sync(_upgrade)


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
        session.add(Prompt(name=name, content=content))
