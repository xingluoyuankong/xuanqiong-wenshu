from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import settings


REVISION = "029_project_members"


def _config() -> Config:
    return Config(str(Path(__file__).parents[2] / "alembic.ini"))


def _upgrade(monkeypatch: pytest.MonkeyPatch, db_path: Path, target: str = "head") -> None:
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    if target == "028_agent_reasoning_chunks" and db_path.exists():
        command.downgrade(_config(), target)
    else:
        command.upgrade(_config(), target)


def test_029_backfills_existing_novel_project_owners_and_is_repeatable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "project-members.sqlite"
    _upgrade(monkeypatch, db_path, "028_agent_reasoning_chunks")
    con = sqlite3.connect(db_path)
    con.execute(
        "insert into users (id, username, hashed_password, is_admin, is_active) values (?, ?, ?, ?, ?)",
        (7001, "migration-owner", "x", 0, 1),
    )
    con.execute(
        "insert into novel_projects (id, user_id, title, status) values (?, ?, ?, ?)",
        ("migration-project-1", 7001, "Migration project", "draft"),
    )
    con.commit()
    con.close()

    _upgrade(monkeypatch, db_path)
    _upgrade(monkeypatch, db_path)

    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == REVISION
    columns = {row[1] for row in con.execute("pragma table_info(project_members)")}
    assert {"id", "project_id", "user_id", "role", "created_at", "updated_at", "deleted_at"} <= columns
    assert con.execute(
        "select project_id, user_id, role, deleted_at from project_members"
    ).fetchall() == [("migration-project-1", 7001, "owner", None)]
    assert con.execute(
        "select count(*) from project_members where project_id = 'migration-project-1'"
    ).fetchone()[0] == 1
    indexes = {row[1] for row in con.execute("pragma index_list(project_members)")}
    assert "ix_project_members_project_id" in indexes
    assert "ix_project_members_user_id" in indexes
    con.close()


def test_029_enforces_project_user_uniqueness_and_downgrades_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "project-members-constraints.sqlite"
    _upgrade(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    con.execute("insert into users (id, username, hashed_password, is_admin, is_active) values (7101, 'u7101', 'x', 0, 1)")
    con.execute("insert into novel_projects (id, user_id, title, status) values ('p7101', 7101, 'p', 'draft')")
    con.execute("insert into project_members (id, project_id, user_id, role) values ('m7101', 'p7101', 7101, 'owner')")
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("insert into project_members (id, project_id, user_id, role) values ('m7102', 'p7101', 7101, 'editor')")
    con.rollback()
    con.close()

    _upgrade(monkeypatch, db_path, "028_agent_reasoning_chunks")
    con = sqlite3.connect(db_path)
    assert con.execute("select name from sqlite_master where type='table' and name='project_members'").fetchone() is None
    assert con.execute("select count(*) from novel_projects where id='p7101'").fetchone()[0] == 1
    con.close()
