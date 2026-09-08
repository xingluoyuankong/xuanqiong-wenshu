"""Default release gate must collect the database invariants, not just feature suites."""
from configparser import ConfigParser
from pathlib import Path


def test_default_pytest_gate_includes_database_regressions():
    config=ConfigParser();config.read(Path(__file__).resolve().parents[2]/'pytest.ini',encoding='utf8')
    paths=set(config['pytest']['testpaths'].split())
    assert {'app/agent','app/services','app/api/routers','app/db'} <= paths
