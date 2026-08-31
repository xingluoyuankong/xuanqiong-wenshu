from pathlib import Path

root = Path(__file__).resolve().parents[2]
config = root / 'pytest.ini'
test_root = root / 'app'
ANYIO_MARK = 'pytest.mark.' + 'anyio'


def test_pytest_runner_uses_one_async_stack():
    """Avoid re-enabling anyio alongside pytest-asyncio auto mode."""
    config_text = config.read_text(encoding='utf-8')
    assert '-p no:anyio' in config_text
    assert 'asyncio_mode = auto' in config_text

    anyio_marks = []
    for path in test_root.rglob('test_*.py'):
        if ANYIO_MARK in path.read_text(encoding='utf-8'):
            anyio_marks.append(path.relative_to(root).as_posix())
    assert not anyio_marks, f'anyio markers must be migrated: {anyio_marks}'
