import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.db import session as db_session


def test_sqlite_generation_pool_registers_one_pragma_listener():
    """SQLite keeps a bounded async queue pool and one per-connection PRAGMA hook."""
    if not db_session.settings.is_sqlite_backend:
        return

    assert isinstance(db_session.engine.sync_engine.pool, AsyncAdaptedQueuePool)
    handlers = [
        handler
        for handler in db_session.engine.sync_engine.pool.dispatch.connect.listeners
        if getattr(handler, "__module__", None) == db_session.__name__
        and getattr(handler, "__name__", None) == "set_sqlite_pragma"
    ]
    assert handlers == [db_session.set_sqlite_pragma]

@pytest.mark.asyncio
async def test_sqlite_foreign_keys_are_enabled_on_real_connections(tmp_path):
    """Project deletion must honor model-level ON DELETE CASCADE in SQLite."""
    if not db_session.settings.is_sqlite_backend:
        return
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'foreign-keys.db'}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine.sync_engine, "connect", db_session.set_sqlite_pragma)
    try:
        async with engine.connect() as connection:
            enabled = await connection.scalar(text("PRAGMA foreign_keys"))
        assert enabled == 1
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_sqlite_foreign_key_cascade_removes_project_children(tmp_path):
    """SQLite cascade semantics must match the model-level project ownership contract."""
    if not db_session.settings.is_sqlite_backend:
        return
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'cascade.db'}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine.sync_engine, "connect", db_session.set_sqlite_pragma)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE novel_projects (id TEXT PRIMARY KEY)"))
            await connection.execute(text("CREATE TABLE chapters (id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES novel_projects(id) ON DELETE CASCADE)"))
            await connection.execute(text("CREATE TABLE token_budgets (id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES novel_projects(id) ON DELETE CASCADE)"))
            await connection.execute(text("INSERT INTO novel_projects (id) VALUES ('p1')"))
            await connection.execute(text("INSERT INTO chapters (id, project_id) VALUES (1, 'p1')"))
            await connection.execute(text("INSERT INTO token_budgets (id, project_id) VALUES (1, 'p1')"))
            await connection.execute(text("DELETE FROM novel_projects WHERE id='p1'"))
            assert await connection.scalar(text("SELECT count(*) FROM chapters")) == 0
            assert await connection.scalar(text("SELECT count(*) FROM token_budgets")) == 0
    finally:
        await engine.dispose()
