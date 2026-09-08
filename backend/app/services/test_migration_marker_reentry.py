"""Repeat failed non-transactional migration without replacing preserved rows."""
from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import create_engine, text, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations

@pytest.mark.parametrize('existing_value',[None,0,1])
def test_ledger_marker_reentry_preserves_existing_value(tmp_path,monkeypatch,existing_value):
 path=Path(__file__).resolve().parents[2]/'alembic/versions/002_ledger_lease_and_runtime_metrics.py'
 spec=importlib.util.spec_from_file_location('marker_migration',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 engine=create_engine(f'sqlite:///{(tmp_path/"marker.sqlite").as_posix()}')
 with engine.begin() as c:
  c.execute(text('CREATE TABLE xq_ledger_lease_migration (id INTEGER PRIMARY KEY, lease_preexisting INTEGER NOT NULL)'))
  if existing_value is not None:c.execute(text('INSERT INTO xq_ledger_lease_migration VALUES (1,:v)'),{'v':existing_value})
  monkeypatch.setattr(module,'op',Operations(MigrationContext.configure(c)))
  module._record_marker(True)
  assert c.execute(text('SELECT lease_preexisting FROM xq_ledger_lease_migration')).scalars().all()==[1 if existing_value is None else existing_value]
  module._record_marker(False)
  assert c.execute(text('SELECT COUNT(*) FROM xq_ledger_lease_migration')).scalar_one()==1
 engine.dispose()
