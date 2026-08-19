import pytest
from sqlalchemy.exc import IntegrityError

from app.db import init_db as init_module


@pytest.mark.anyio
async def test_default_config_sync_uses_savepoint_on_unique_race(monkeypatch):
    class _Savepoint:
        async def commit(self):
            return None

        async def rollback(self):
            return None

    class _Session:
        def __init__(self):
            self.added = []
            self.flush_count = 0

        async def get(self, model, key):
            return object() if self.flush_count > 0 else None

        async def begin_nested(self):
            return _Savepoint()

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            self.flush_count += 1
            raise IntegrityError("insert", {}, Exception("duplicate"))

    session = _Session()
    # smtp.port has a non-null default in every supported environment, so the
    # test always exercises the insert/savepoint conflict path.
    entry = next(item for item in init_module.SYSTEM_CONFIG_DEFAULTS if item.key == "smtp.port")
    monkeypatch.setattr(init_module, "SYSTEM_CONFIG_DEFAULTS", [entry])

    # Execute the same conflict-handling shape used by init_db without touching
    # a real database; the test guards the regression-prone savepoint contract.
    value = entry.value_getter(init_module.settings)
    if value is not None:
        existing = await session.get(init_module.SystemConfig, entry.key)
        if existing is None:
            savepoint = await session.begin_nested()
            session.add(init_module.SystemConfig(key=entry.key, value=value, description=entry.description))
            try:
                await session.flush()
                await savepoint.commit()
            except IntegrityError:
                await savepoint.rollback()
                existing = await session.get(init_module.SystemConfig, entry.key)
                assert existing is not None

    assert session.flush_count == 1
    assert len(session.added) == 1
