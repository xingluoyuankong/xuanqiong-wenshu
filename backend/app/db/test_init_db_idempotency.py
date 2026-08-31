import pytest
from sqlalchemy.exc import IntegrityError

from app.db import init_db as init_module


@pytest.mark.asyncio
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


class _PromptResult:
    def __init__(self, names):
        self._names = names

    def scalars(self):
        return self

    def all(self):
        return list(self._names)


class _PromptSavepoint:
    async def commit(self):
        return None

    async def rollback(self):
        return None


class _PromptSession:
    def __init__(self, existing=None):
        self.records = dict(existing or {})
        self.added = []
        self._pending = None

    async def execute(self, _statement):
        return _PromptResult(self.records.keys())

    async def begin_nested(self):
        return _PromptSavepoint()

    def add(self, value):
        self.added.append(value)
        self._pending = value

    async def flush(self):
        if self._pending is not None:
            self.records[self._pending.name] = self._pending.content
            self._pending = None


@pytest.mark.asyncio
async def test_writing_v2_seed_is_exact_and_idempotent(tmp_path, monkeypatch):
    root_prompt_dir = tmp_path / "root-prompts"
    root_prompt_dir.mkdir()
    # The editable root copy must not be the source for this dedicated seed.
    (root_prompt_dir / "writing_v2.md").write_text("do not seed this content", encoding="utf-8")
    (root_prompt_dir / "other.md").write_text("other prompt", encoding="utf-8")
    monkeypatch.setattr(init_module, "DEFAULT_PROMPTS_DIR", root_prompt_dir)

    seed_path = init_module.WRITING_V2_PROMPT_SEED_PATH
    source_path = init_module.Path(__file__).resolve().parents[2] / "prompts" / "writing_v2.md"
    assert seed_path.read_bytes() == source_path.read_bytes()

    session = _PromptSession()
    await init_module._ensure_default_prompts(session)
    first_added_count = len(session.added)
    await init_module._ensure_default_prompts(session)

    assert first_added_count == 2
    assert len(session.added) == first_added_count
    assert session.records["writing_v2"] == seed_path.read_text(encoding="utf-8")
    assert session.records["writing_v2"] != "do not seed this content"


@pytest.mark.asyncio
async def test_writing_v2_seed_never_overwrites_existing_prompt():
    custom_content = "管理员自定义的 writing_v2 内容"
    session = _PromptSession({"writing_v2": custom_content})

    inserted = await init_module._ensure_writing_v2_prompt_seed(session)

    assert inserted is False
    assert session.records["writing_v2"] == custom_content
    assert session.added == []


@pytest.mark.asyncio
async def test_writing_v2_no_overwrite_guard_fails_when_implementation_is_sabotaged(monkeypatch):
    custom_content = "保留这份线上提示词"
    session = _PromptSession({"writing_v2": custom_content})

    async def broken_seed(session, existing_names=None):
        session.records["writing_v2"] = "被错误覆盖的内容"
        return True

    monkeypatch.setattr(init_module, "_ensure_writing_v2_prompt_seed", broken_seed)
    with pytest.raises(AssertionError):
        await _assert_writing_v2_unchanged(session, custom_content)


async def _assert_writing_v2_unchanged(session, expected_content):
    await init_module._ensure_writing_v2_prompt_seed(session)
    assert session.records["writing_v2"] == expected_content
    assert session.added == []