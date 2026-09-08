"""Connection lease UTC invariants; no live database required for unit tests."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import event, pool


class Cursor:
    def __init__(self, connection): self.connection=connection; self.closed=False
    def execute(self,sql):
        self.connection.statements.append(sql)
        if self.connection.fail: raise RuntimeError('timezone setup failed')
        assert sql == "SET SESSION time_zone = '+00:00'"
        self.connection.timezone='+00:00'
    def close(self): self.closed=True


class Connection:
    def __init__(self,fail=False):
        self.timezone='+08:00';self.fail=fail;self.statements=[];self.cursors=[]
    def cursor(self):
        c=Cursor(self);self.cursors.append(c);return c


@pytest.mark.asyncio
async def test_application_pool_checkout_restores_utc_each_borrow(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings,'database_url','mysql+asyncmy://fixture:fixture@127.0.0.1:1/fixture')
    # Import with its actual relative-import package, but do not replace cached app engine.
    path=Path(__file__).with_name('session.py')
    ns={'__name__':'app.db._timezone_policy_test','__package__':'app.db','__file__':str(path)}
    exec(compile(path.read_text(encoding='utf-8-sig'),str(path),'exec'),ns)
    engine=ns['engine']
    try:
        connection=Connection()
        engine.sync_engine.pool.dispatch.checkout(connection,None,None)
        assert connection.timezone=='+00:00'
        connection.timezone='-05:00'
        engine.sync_engine.pool.dispatch.checkout(connection,None,None)
        assert connection.timezone=='+00:00'
        assert len(connection.statements)==2
        assert all(c.closed for c in connection.cursors)
    finally: await engine.dispose()


@pytest.mark.asyncio
async def test_migration_engine_has_checkout_policy_before_connect(monkeypatch):
    path=Path(__file__).resolve().parents[2]/'alembic/env.py'
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='run_async_migrations')
    engine=create_async_engine('mysql+asyncmy://fixture:fixture@127.0.0.1:1/fixture')
    connection=Connection();seen=[]
    class Context:
        async def __aenter__(self):
            engine.sync_engine.pool.dispatch.checkout(connection,None,None)
            assert connection.timezone=='+00:00'
            seen.append('utc_before_migration')
            return SimpleNamespace(run_sync=AsyncMock())
        async def __aexit__(self,*args):pass
    proxy=SimpleNamespace(sync_engine=engine.sync_engine,connect=lambda:Context(),dispose=AsyncMock())
    ns={'config':SimpleNamespace(config_ini_section='alembic',get_section=lambda *a:{}),
        'pool':pool,'async_engine_from_config':lambda *a,**kw:proxy,'do_run_migrations':lambda conn:None}
    # Import the future helper only when that import exists in the actual module.
    for node in tree.body:
        if isinstance(node,ast.ImportFrom) and node.module=='app.db.mysql_timezone':
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    try:
        await ns['run_async_migrations']()
        assert seen==['utc_before_migration']
        proxy.dispose.assert_awaited_once()
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_pool_never_runs_mysql_timezone_sql():
    from app.db.mysql_timezone import install_mysql_utc_policy
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        install_mysql_utc_policy(engine)
        connection=Connection()
        engine.sync_engine.pool.dispatch.checkout(connection,None,None)
        assert connection.statements==[]
        async with engine.connect() as c: assert await c.run_sync(lambda conn:conn.exec_driver_sql('SELECT 1').scalar())==1
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_mysql_policy_is_idempotent_and_applies_on_connect_and_checkout():
    from app.db.mysql_timezone import install_mysql_utc_policy, _set_mysql_utc
    engine=create_async_engine('mysql+asyncmy://fixture:fixture@127.0.0.1:1/fixture')
    try:
        install_mysql_utc_policy(engine);install_mysql_utc_policy(engine)
        assert event.contains(engine.sync_engine,'connect',_set_mysql_utc)
        assert event.contains(engine.sync_engine,'checkout',_set_mysql_utc)
        c=Connection();engine.sync_engine.pool.dispatch.checkout(c,None,None)
        assert c.statements==["SET SESSION time_zone = '+00:00'"]
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_failed_timezone_setup_closes_cursor_and_rejects_checkout():
    from app.db.mysql_timezone import install_mysql_utc_policy
    engine=create_async_engine('mysql+asyncmy://fixture:fixture@127.0.0.1:1/fixture')
    try:
        install_mysql_utc_policy(engine);c=Connection(fail=True)
        with pytest.raises(RuntimeError,match='timezone setup failed'):
            engine.sync_engine.pool.dispatch.checkout(c,None,None)
        assert c.cursors[0].closed
        assert c.timezone=='+08:00'
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_create_database_engine_has_policy_before_admin_connection(monkeypatch):
    from app.db import init_db
    monkeypatch.setattr(init_db.settings,'database_url','mysql+asyncmy://fixture:fixture@127.0.0.1:1/fixture')
    engine=create_async_engine('mysql+asyncmy://fixture:fixture@127.0.0.1:1/fixture')
    connection=Connection();queries=[]
    class Context:
        async def __aenter__(self):
            engine.sync_engine.pool.dispatch.checkout(connection,None,None)
            assert connection.timezone=='+00:00'
            async def execute(sql):queries.append(str(sql))
            return SimpleNamespace(execute=execute)
        async def __aexit__(self,*args):pass
    proxy=SimpleNamespace(sync_engine=engine.sync_engine,begin=lambda:Context(),dispose=AsyncMock())
    monkeypatch.setattr(init_db,'create_async_engine',lambda *a,**kw:proxy)
    try:
        await init_db._ensure_database_exists()
        assert queries==['CREATE DATABASE IF NOT EXISTS `fixture`']
        proxy.dispose.assert_awaited_once()
    finally:await engine.dispose()
