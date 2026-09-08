"""Pin MySQL connection leases to UTC without changing server global state."""
from sqlalchemy import event


def _set_mysql_utc(dbapi_connection, *_pool_context):
    # SQLAlchemy's async DBAPI adapter bridges this synchronous event callback
    # into the async driver. Exceptions propagate: a non-UTC lease must not be
    # handed to a caller when session initialization fails.
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET SESSION time_zone = '+00:00'")
    finally:
        cursor.close()


def install_mysql_utc_policy(engine):
    """Set UTC on physical connect and every pool checkout (including reuse)."""
    target = getattr(engine, 'sync_engine', engine)
    if target.dialect.name != 'mysql':
        return
    for name in ('connect', 'checkout'):
        if not event.contains(target, name, _set_mysql_utc):
            event.listen(target, name, _set_mysql_utc)
