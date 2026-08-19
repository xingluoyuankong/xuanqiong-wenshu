"""异步 Alembic 运行环境。

数据库连接串统一来自 app.core.config.settings.sqlalchemy_database_uri；
alembic.ini 中的 URL 仅作为可读的安全回退值，不作为运行时真相源。
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.db.base import Base

# 导入模型，保证 autogenerate 与目标元数据包含所有已注册模型。
import app.models  # noqa: F401,E402


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser 使用 % 作为插值标记；密码中可能出现百分号，写入配置时必须转义。
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_uri.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """以无需建立连接的方式生成 SQL。"""
    context.configure(
        url=settings.sqlalchemy_database_uri,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """在同步连接适配器中运行迁移，由异步连接 run_sync 调用。"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """创建异步引擎并在同步适配器中执行 Alembic 操作。"""
    section = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口；Alembic CLI 本身是同步入口，因此在此启动事件循环。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
