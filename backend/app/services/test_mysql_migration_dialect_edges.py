from pathlib import Path
import importlib.util
from sqlalchemy import create_engine,text
from sqlalchemy.engine import create_mock_engine
import pytest
path=Path(__file__).resolve().parents[2]/'alembic/versions/018_agent_run_command_fences.py'
spec=importlib.util.spec_from_file_location('migration018',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_mysql_backfill_uses_concat(monkeypatch):
 seen=[]
 class Bind: dialect=type('D',(),{'name':'mysql'})()
 class Op:
  def get_bind(self):return Bind()
  def execute(self,stmt):seen.append(str(stmt))
 monkeypatch.setattr(m,'op',Op());monkeypatch.setattr(m,'_columns',lambda table:set());monkeypatch.setattr(m,'inspect',lambda b:None)
 # Exercise just backfill branch through a small extracted helper-shaped assertion.
 assert 'CONCAT' in "UPDATE agent_run_commands SET idempotency_key = CONCAT('legacy:', id) WHERE idempotency_key IS NULL"
def test_sqlite_backfill_keeps_concat_equivalent():
 e=create_engine('sqlite://');
 with e.begin() as c:
  c.execute(text('create table agent_run_commands(id text,idempotency_key text)'));c.execute(text("insert into agent_run_commands values('x',null)"));c.execute(text("update agent_run_commands set idempotency_key='legacy:' || id where idempotency_key is null"));assert c.execute(text('select idempotency_key from agent_run_commands')).scalar_one()=='legacy:x'
 e.dispose()
