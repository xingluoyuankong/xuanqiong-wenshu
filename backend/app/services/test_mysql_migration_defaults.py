"""Every explicit migration JSON/TEXT default must compile as a MySQL expression."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.schema import CreateColumn

VERSIONS = Path(__file__).resolve().parents[2] / 'alembic' / 'versions'

def cases():
    for path in sorted(VERSIONS.glob('*.py')):
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                and node.func.attr=='Column' and len(node.args)>1
                and isinstance(node.args[1],ast.Call) and isinstance(node.args[1].func,ast.Attribute)
                and node.args[1].func.attr in {'JSON','Text','LargeBinary'}
                and any(k.arg=='server_default' for k in node.keywords)):
                yield pytest.param(path,node,id=f'{path.stem}:{node.lineno}')

@pytest.mark.parametrize('path,node',list(cases()))
def test_migration_large_value_default_is_mysql_expression(path,node,monkeypatch):
    spec=importlib.util.spec_from_file_location(f'test_default_{path.stem}',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.op,'get_bind',lambda:SimpleNamespace(dialect=mysql.dialect()))
    column=eval(compile(ast.Expression(body=node),str(path),'eval'),module.__dict__)
    if column.server_default is None:return
    sql=str(CreateColumn(column).compile(dialect=mysql.dialect()))
    assert 'DEFAULT (' in sql,sql
    # SQLite must still be able to emit the same column definition.
    assert str(CreateColumn(column).compile(dialect=sqlite.dialect()))
