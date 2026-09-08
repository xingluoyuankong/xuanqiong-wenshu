"""Research schema regressions using fresh Alembic processes and temporary DBs."""
from __future__ import annotations

import ast
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[2]
MIGRATIONS = BACKEND / "alembic"
PREVIOUS = "029_project_members"
REVISION = "030_research_schema_repair"
TABLES = ("project_research_configs", "research_artifacts")


def _alembic(db: Path, action: str = "upgrade", target: str = REVISION, *, scripts: Path = MIGRATIONS) -> None:
    # Do not use the parent process's settings or imported ORM metadata: doing so
    # hid the original fresh-process failure. Explicit URLs never touch real DBs.
    env = os.environ.copy()
    env.update(
        DATABASE_URL=f"sqlite+aiosqlite:///{db.as_posix()}",
        DB_PROVIDER="sqlite",
        XUANQIONG_TEST_LIGHT_IMPORTS="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; from alembic import command; from alembic.config import Config; "
            "c = Config(sys.argv[1]); c.set_main_option('script_location', sys.argv[2]); "
            "getattr(command, sys.argv[3])(c, sys.argv[4])",
            str(BACKEND / "alembic.ini"), str(scripts), action, target,
        ],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _schema_matches_models(db: Path) -> None:
    # Import only AFTER the independent Alembic process has finished.
    from app.models.research import ProjectResearchConfig, ResearchArtifact

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        inspector = sa.inspect(engine)
        assert set(TABLES) <= set(inspector.get_table_names()), "missing research tables"
        for model in (ProjectResearchConfig, ResearchArtifact):
            table = model.__table__
            columns = {c["name"]: c for c in inspector.get_columns(table.name)}
            assert set(columns) == set(table.columns.keys())
            for column in table.columns:
                actual = columns[column.name]
                assert str(actual["type"]) == str(column.type.compile(dialect=engine.dialect))
                assert actual["nullable"] == column.nullable
                expected_default = (
                    str(column.server_default.arg.compile(dialect=engine.dialect))
                    if column.server_default is not None else None
                )
                assert actual["default"] == expected_default
            assert inspector.get_pk_constraint(table.name)["constrained_columns"] == [
                c.name for c in table.primary_key.columns
            ]
            assert {
                (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]), f["options"].get("ondelete"))
                for f in inspector.get_foreign_keys(table.name)
            } == {
                ((f.parent.name,), f.column.table.name, (f.column.name,), f.ondelete)
                for f in table.foreign_keys
            }
            actual_indexes = {
                (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                for i in inspector.get_indexes(table.name)
            }
            assert {(i.name, tuple(c.name for c in i.columns), bool(i.unique)) for i in table.indexes} <= actual_indexes
            assert {
                (c.name, tuple(col.name for col in c.columns))
                for c in table.constraints if isinstance(c, sa.UniqueConstraint)
            } <= {
                (c["name"], tuple(c["column_names"]))
                for c in inspector.get_unique_constraints(table.name)
            }
    finally:
        engine.dispose()


def _revision(db: Path) -> str:
    with closing(sqlite3.connect(db)) as con:
        return con.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def _rows(db: Path) -> dict:
    with closing(sqlite3.connect(db)) as con:
        return {table: con.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall() for table in TABLES}


def _seed_parents(db: Path) -> None:
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("INSERT INTO users (id, username, hashed_password, is_admin, is_active) VALUES (8801, 'research-migration-owner', 'x', 0, 1)")
        con.execute("INSERT INTO novel_projects (id, user_id, title, status) VALUES ('research-sentinel', 8801, 'sentinel project', 'draft')")


def _seed_research(db: Path) -> None:
    from app.models.research import ProjectResearchConfig, ResearchArtifact

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.begin() as con:
            con.exec_driver_sql("PRAGMA foreign_keys=ON")
            con.execute(ProjectResearchConfig.__table__.insert().values(
                project_id="research-sentinel", mode="manual",
                search_api_key_encrypted="opaque-sentinel-ciphertext",
                preferred_domains=["example.org"], extra={"sentinel": "研究配置"},
            ))
            con.execute(ResearchArtifact.__table__.insert().values(
                id=8802, project_id="research-sentinel", user_id=8801,
                run_id="research-sentinel-run", scope="global", status="completed",
                summary="sentinel: 已有研究成果", sources=[{"title": "source-sentinel"}],
                category_payload={"sentinel": [1, 2]}, file_manifest={"path": "sentinel.json"},
            ))
    finally:
        engine.dispose()


def _create_existing_tables(db: Path) -> None:
    from app.models.research import ProjectResearchConfig, ResearchArtifact

    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.begin() as con:
            for model in (ProjectResearchConfig, ResearchArtifact):
                model.__table__.create(con, checkfirst=True)
    finally:
        engine.dispose()


@pytest.fixture
def legacy_029(tmp_path: Path) -> Path:
    db = tmp_path / "legacy-029.sqlite"
    _alembic(db, target=PREVIOUS)
    # Simulate the historical import-order gap even after model exports are fixed.
    with closing(sqlite3.connect(db)) as con, con:
        for table in reversed(TABLES):
            con.execute(f'DROP TABLE IF EXISTS "{table}"')
    _seed_parents(db)
    assert _revision(db) == PREVIOUS
    return db


def test_fresh_subprocess_upgrade_and_repeat(tmp_path: Path) -> None:
    db = tmp_path / "fresh.sqlite"
    _alembic(db)
    _schema_matches_models(db)
    assert _revision(db) == REVISION
    _seed_parents(db)
    _seed_research(db)
    before = _rows(db)
    _alembic(db)
    assert _rows(db) == before
    _schema_matches_models(db)


def test_029_missing_tables_are_repaired(legacy_029: Path) -> None:
    _alembic(legacy_029)
    assert _revision(legacy_029) == REVISION
    _schema_matches_models(legacy_029)
    _seed_research(legacy_029)
    assert all(_rows(legacy_029).values())
    with closing(sqlite3.connect(legacy_029)) as con:
        assert con.execute("SELECT title FROM novel_projects WHERE id='research-sentinel'").fetchone() == ("sentinel project",)
        assert con.execute("SELECT username FROM users WHERE id=8801").fetchone() == ("research-migration-owner",)


@pytest.mark.parametrize("existing", [(), (TABLES[0],), (TABLES[1],), TABLES])
def test_029_partial_or_existing_tables_preserve_every_sentinel(legacy_029: Path, existing: tuple) -> None:
    _create_existing_tables(legacy_029)
    _seed_research(legacy_029)
    before = _rows(legacy_029)
    with closing(sqlite3.connect(legacy_029)) as con, con:
        for table in TABLES:
            if table not in existing:
                con.execute(f'DROP TABLE "{table}"')
    _alembic(legacy_029)
    _schema_matches_models(legacy_029)
    after = _rows(legacy_029)
    for table in existing:
        assert after[table] == before[table]
    for table in set(TABLES) - set(existing):
        assert after[table] == []
    _alembic(legacy_029)
    assert _rows(legacy_029) == after


@pytest.mark.parametrize("preexisting", [False, True])
def test_downgrade_and_reupgrade_preserve_research(legacy_029: Path, preexisting: bool) -> None:
    if preexisting:
        _create_existing_tables(legacy_029)
        _seed_research(legacy_029)
    _alembic(legacy_029)
    if not preexisting:
        _seed_research(legacy_029)
    before = _rows(legacy_029)
    for _ in range(2):
        _alembic(legacy_029, "downgrade", PREVIOUS)
        assert _revision(legacy_029) == PREVIOUS
        _schema_matches_models(legacy_029)
        assert _rows(legacy_029) == before
        _alembic(legacy_029)
        assert _revision(legacy_029) == REVISION
        _schema_matches_models(legacy_029)
        assert _rows(legacy_029) == before


def test_missing_indexes_repaired_without_rebuilding_existing_table(legacy_029: Path) -> None:
    _create_existing_tables(legacy_029)
    _seed_research(legacy_029)
    before = _rows(legacy_029)
    with closing(sqlite3.connect(legacy_029)) as con, con:
        indexes = con.execute("PRAGMA index_list(research_artifacts)").fetchall()
        for index in indexes:
            if index[1].startswith("ix_research_artifacts_"):
                con.execute(f'DROP INDEX "{index[1]}"')
        con.execute("CREATE INDEX sentinel_custom_index ON research_artifacts(summary)")
        sql_before = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='research_artifacts'").fetchone()
    _alembic(legacy_029)
    _schema_matches_models(legacy_029)
    assert _rows(legacy_029) == before
    with closing(sqlite3.connect(legacy_029)) as con:
        assert "sentinel_custom_index" in {r[1] for r in con.execute("PRAGMA index_list(research_artifacts)")}
        assert con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='research_artifacts'").fetchone() == sql_before


def test_repaired_schema_enforces_uniqueness_and_foreign_keys(legacy_029: Path) -> None:
    _alembic(legacy_029)
    _seed_research(legacy_029)
    with closing(sqlite3.connect(legacy_029)) as con:
        con.execute("PRAGMA foreign_keys=ON")
        insert = "INSERT INTO research_artifacts (project_id, user_id, run_id, scope, status, trigger) VALUES (?, ?, ?, 'global', 'completed', 'manual')"
        for values, message in [
            (("research-sentinel", 8801, "research-sentinel-run"), "UNIQUE"),
            (("missing-project", 8801, "new-run"), "FOREIGN KEY"),
            (("research-sentinel", 999999, "new-run"), "FOREIGN KEY"),
        ]:
            with pytest.raises(sqlite3.IntegrityError, match=message):
                con.execute(insert, values)
            con.rollback()
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def _mutated_scripts(tmp_path: Path, function: str, body: str) -> Path:
    scripts = tmp_path / f"mutant-{function}"
    shutil.copytree(MIGRATIONS, scripts, ignore=shutil.ignore_patterns("__pycache__"))
    migration = scripts / "versions" / f"{REVISION}.py"
    source = migration.read_text(encoding="utf-8-sig")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == function)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [f"def {function}() -> None:\n", f"    {body}\n"]
    migration.write_text("".join(lines), encoding="utf-8")
    return scripts


def test_reverse_validation_rejects_noop_upgrade(legacy_029: Path, tmp_path: Path) -> None:
    scripts = _mutated_scripts(tmp_path, "upgrade", "pass")
    _alembic(legacy_029, scripts=scripts)
    # A version stamp alone is not success: the same schema oracle must fail.
    assert _revision(legacy_029) == REVISION
    with pytest.raises(AssertionError, match="missing research tables"):
        _schema_matches_models(legacy_029)


def test_reverse_validation_rejects_destructive_downgrade(legacy_029: Path, tmp_path: Path) -> None:
    _alembic(legacy_029)
    _seed_research(legacy_029)
    scripts = _mutated_scripts(tmp_path, "downgrade", "op.drop_table('research_artifacts')")
    _alembic(legacy_029, "downgrade", PREVIOUS, scripts=scripts)
    with pytest.raises(AssertionError, match="missing research tables"):
        _schema_matches_models(legacy_029)
