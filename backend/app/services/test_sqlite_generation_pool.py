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