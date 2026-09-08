from pathlib import Path
import ast
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from sqlalchemy import String, create_engine, inspect
from sqlalchemy.dialects import mysql
from app.db import migration_version as module


def test_all_published_revision_ids_fit_version_table():
    versions=Path(__file__).resolve().parents[2]/'alembic/versions'
    ids=[]
    for path in versions.glob('*.py'):
        for n in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='revision':
                ids.append(ast.literal_eval(n.value))
    assert max(map(len,ids))>32
    assert max(map(len,ids))<=module.VERSION_ID_LENGTH

@pytest.mark.parametrize('length,alter',[(32,True),(64,True),(128,False),(255,False)])
def test_widens_only_insufficient_mysql_version_column(monkeypatch,length,alter):
    inspector=Mock();inspector.has_table.return_value=True
    inspector.get_columns.return_value=[{'name':'version_num','type':String(length)}]
    monkeypatch.setattr(module,'inspect',lambda c:inspector)
    conn=Mock();conn.dialect.name='mysql'
    module.ensure_mysql_version_table(conn)
    assert conn.exec_driver_sql.call_count==int(alter)
    if alter:assert conn.exec_driver_sql.call_args.args==('ALTER TABLE alembic_version MODIFY version_num VARCHAR(128) NOT NULL',)


def test_sqlite_version_records_are_not_touched():
    engine=create_engine('sqlite://')
    with engine.begin() as c:
        module.ensure_mysql_version_table(c)
        assert not inspect(c).has_table('alembic_version')
    engine.dispose()


def test_fresh_mysql_version_table_has_capacity_and_primary_key(monkeypatch):
    from sqlalchemy import create_mock_engine
    statements=[]
    engine=create_mock_engine('mysql://',lambda sql,*a,**k:statements.append(str(sql.compile(dialect=mysql.dialect()))))
    inspector=Mock();inspector.has_table.return_value=False
    monkeypatch.setattr(module,'inspect',lambda c:inspector)
    module.ensure_mysql_version_table(engine)
    assert len(statements)==1
    assert 'VARCHAR(128)' in statements[0] and 'PRIMARY KEY (version_num)' in statements[0]
