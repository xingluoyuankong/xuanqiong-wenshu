import argparse
import asyncio
import sys
from pathlib import Path
from typing import Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from urllib.parse import quote_plus

from sqlalchemy import select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401  # 确保所有 ORM 模型已注册到 metadata


def _resolve_sqlite_path(raw_path: str | None) -> Path:
    candidate = Path((raw_path or "storage/xuanqiong_wenshu.db").strip()).expanduser()
    if not candidate.is_absolute():
        candidate = (settings.project_root / candidate).resolve()
    return candidate


def _build_default_source_url() -> str:
    db_path = _resolve_sqlite_path(settings.sqlite_db_path)
    return f"sqlite+aiosqlite:///{db_path}"


def _build_default_target_url() -> str:
    encoded_password = quote_plus(settings.mysql_password)
    database = (settings.mysql_database or "").strip("/")
    return (
        f"mysql+asyncmy://{settings.mysql_user}:{encoded_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{database}"
    )


def _normalize_async_url(raw_url: str, *, expected_backend: str) -> str:
    url = make_url(raw_url)
    backend = url.get_backend_name()
    if backend != expected_backend:
        raise ValueError(f"URL 后端必须是 {expected_backend}，当前为 {backend}")

    drivername = "sqlite+aiosqlite" if expected_backend == "sqlite" else "mysql+asyncmy"
    normalized = URL.create(
        drivername=drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=(url.database or "").strip("/") or None,
        query=url.query,
    )
    return normalized.render_as_string(hide_password=False)


def _mask_url(raw_url: str) -> str:
    return make_url(raw_url).render_as_string(hide_password=True)


async def _ensure_mysql_database_exists(target_url: str) -> None:
    url = make_url(target_url)
    database = (url.database or "").strip("/")
    if not database:
        raise ValueError("目标 MySQL URL 缺少数据库名")

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
        escaped_database = database.replace("`", "``")
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{escaped_database}`"))
    finally:
        await admin_engine.dispose()


async def _create_target_schema(target_url: str) -> None:
    engine = create_async_engine(target_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _assert_target_empty(target_conn: AsyncConnection, tables: Sequence) -> None:
    for table in tables:
        first_column = next(iter(table.c), None)
        if first_column is None:
            continue
        result = await target_conn.execute(select(first_column).select_from(table).limit(1))
        if result.first() is not None:
            raise RuntimeError(f"目标库非空：表 {table.name} 已存在数据，迁移已中止")


async def _copy_table(
    source_conn: AsyncConnection,
    target_conn: AsyncConnection,
    table,
    *,
    chunk_size: int,
) -> int:
    inserted = 0
    stream = await source_conn.stream(select(table))
    async for batch in stream.partitions(chunk_size):
        payload = [dict(row._mapping) for row in batch]
        if not payload:
            continue
        await target_conn.execute(table.insert(), payload)
        inserted += len(payload)
    return inserted


async def migrate(*, source_url: str, target_url: str, chunk_size: int) -> None:
    tables = list(Base.metadata.sorted_tables)
    if not tables:
        raise RuntimeError("未发现可迁移的 ORM 表")

    await _ensure_mysql_database_exists(target_url)
    await _create_target_schema(target_url)

    source_engine = create_async_engine(source_url)
    target_engine = create_async_engine(target_url, pool_pre_ping=True)
    total_rows = 0

    try:
        async with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
            await _assert_target_empty(target_conn, tables)
            await target_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            await target_conn.commit()
            try:
                for table in tables:
                    tx = await target_conn.begin()
                    try:
                        copied_rows = await _copy_table(
                            source_conn,
                            target_conn,
                            table,
                            chunk_size=chunk_size,
                        )
                        await tx.commit()
                    except Exception:
                        await tx.rollback()
                        raise

                    total_rows += copied_rows
                    print(f"[正常] {table.name}：已复制 {copied_rows} 行")
            finally:
                await target_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
                await target_conn.commit()
    finally:
        await source_engine.dispose()
        await target_engine.dispose()

    print(f"迁移完成，共复制 {total_rows} 行。")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 SQLite 数据迁移到 MySQL")
    parser.add_argument("--source-url", help="源 SQLite URL，默认读取当前项目 SQLite 配置")
    parser.add_argument("--source-sqlite-path", help="源 SQLite 文件路径，优先级低于 --source-url")
    parser.add_argument("--target-url", help="目标 MySQL URL，默认读取当前项目 MySQL 配置")
    parser.add_argument("--chunk-size", type=int, default=500, help="单批插入行数，默认 500")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    source_url = _normalize_async_url(args.source_url, expected_backend="sqlite") if args.source_url else None
    if not source_url:
        if args.source_sqlite_path:
            source_url = f"sqlite+aiosqlite:///{_resolve_sqlite_path(args.source_sqlite_path)}"
        else:
            source_url = _build_default_source_url()

    target_url = _normalize_async_url(args.target_url, expected_backend="mysql") if args.target_url else _build_default_target_url()

    if make_url(source_url).get_backend_name() != "sqlite":
        raise ValueError("源库必须是 SQLite")
    if make_url(target_url).get_backend_name() != "mysql":
        raise ValueError("目标库必须是 MySQL")
    if source_url == target_url:
        raise ValueError("源库与目标库不能相同")
    if args.chunk_size <= 0:
        raise ValueError("chunk-size 必须大于 0")

    print(f"源库：{_mask_url(source_url)}")
    print(f"目标库：{_mask_url(target_url)}")
    await migrate(source_url=source_url, target_url=target_url, chunk_size=args.chunk_size)


if __name__ == "__main__":
    asyncio.run(main())
