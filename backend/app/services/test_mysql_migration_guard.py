import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_sqlite_to_mysql.py"
spec = importlib.util.spec_from_file_location("migrate_sqlite_to_mysql", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_preview_never_connects_or_writes():
    preview = module._render_preview(
        source_url="sqlite+aiosqlite:///tmp/source.db",
        target_url="mysql+asyncmy://root:secret@mysql/db",
        chunk_size=500,
        table_count=57,
    )
    assert '"execute": false' in preview
    assert '"connected": false' in preview
    assert '"writes_performed": false' in preview
    assert "secret" not in preview


def test_apply_requires_backup_manifest():
    with pytest.raises(ValueError, match="backup-manifest"):
        module._load_backup_manifest(None)
