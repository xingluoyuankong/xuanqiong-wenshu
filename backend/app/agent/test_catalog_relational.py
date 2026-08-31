from __future__ import annotations

from pathlib import Path

import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.agent.catalog_release import build_catalog_release
from app.agent.capability_resolver import resolve_capabilities
from app.agent.registry import get_default_tool_registry_snapshot
from app.models import (
    AgentCapabilityDefinition,
    AgentCapabilityExecution,
    AgentCatalogRelease,
    AgentProviderRelease,
    AgentRunCapabilitySnapshot,
    NovelProject,
    User,
)
from app.services.agent_runtime import AgentRuntimeService
from app.core.config import settings


EXPECTED_TABLES = {
    "agent_catalog_releases",
    "agent_provider_releases",
    "agent_capability_definitions",
    "agent_run_capability_snapshots",
    "agent_capability_executions",
}


@pytest.mark.asyncio
async def test_relational_catalog_entities_persist_and_link(task_session):
    """create_run writes one reusable Catalog Release and one Run-local snapshot."""
    user = User(id=2701, username="catalog-relational", email="catalog-relational@example.com", hashed_password="x", is_active=True)
    project = NovelProject(id="catalog-relational-project", user_id=user.id, title="Catalog relational")
    task_session.add_all([user, project])
    await task_session.flush()

    runtime = AgentRuntimeService(task_session)
    agent_session = await runtime.create_session(user_id=user.id, project_id=project.id)
    run = await runtime.create_run(
        session_id=agent_session.id,
        user_id=user.id,
        project_id=project.id,
        context={"requested_tools": ["project.list"]},
    )

    release = (await task_session.execute(select(AgentCatalogRelease))).scalar_one()
    providers = list((await task_session.execute(select(AgentProviderRelease))).scalars().all())
    definitions = list((await task_session.execute(select(AgentCapabilityDefinition))).scalars().all())
    snapshot = (await task_session.execute(select(AgentRunCapabilitySnapshot).where(AgentRunCapabilitySnapshot.run_id == run.id))).scalar_one()
    capability = next(item for item in definitions if item.capability_id == "project.list")

    assert release.release_id == run.context_json["catalog_release_id"]
    assert release.digest == run.context_json["catalog_release"]["digest"]
    assert providers
    assert len(definitions) == len(release.manifest_json["tools"])
    assert snapshot.transaction_id == run.transaction_id
    assert snapshot.catalog_release_id == release.id
    assert snapshot.id == run.context_json["relational_capability_snapshot_id"]
    assert snapshot.snapshot_id == run.context_json["relational_capability_snapshot_key"]
    assert snapshot.selected_capability_ids_json == ["project.list"]

    execution = AgentCapabilityExecution(
        execution_id="execution-catalog-2701",
        run_id=run.id,
        transaction_id=run.transaction_id,
        step_id=None,
        snapshot_id=snapshot.id,
        capability_definition_id=capability.id,
        provider_release_id=capability.provider_release_id,
        correlation_id=run.correlation_id,
        capability_id=capability.capability_id,
        resolved_version=capability.version,
        status="completed",
        idempotency_key="exec-catalog-2701",
        input_json={},
        output_json={"ok": True},
        input_digest="a" * 64,
        output_digest="b" * 64,
    )
    task_session.add(execution)
    await task_session.commit()

    saved = (await task_session.execute(select(AgentCapabilityExecution).where(AgentCapabilityExecution.execution_id == execution.execution_id))).scalar_one()
    assert saved.snapshot_id == snapshot.id
    assert saved.capability_definition_id == capability.id
    assert saved.transaction_id == run.transaction_id

@pytest.mark.asyncio
async def test_provider_release_uniqueness_is_enforced_per_catalog(task_session):
    user = User(id=2702, username="catalog-unique", email="catalog-unique@example.com", hashed_password="x", is_active=True)
    task_session.add(user)
    await task_session.flush()
    release = AgentCatalogRelease(
        release_id="agent-catalog-release-v1:unique", catalog_id="agent-catalog-release-v1",
        generation=901, digest="e" * 64, manifest_json={}, status="published",
    )
    task_session.add(release)
    await task_session.flush()
    task_session.add_all([
        AgentProviderRelease(id="provider-unique-a", catalog_release_id=release.id, provider_id="same-provider", source="test", status="loaded"),
        AgentProviderRelease(id="provider-unique-b", catalog_release_id=release.id, provider_id="same-provider", source="test", status="loaded"),
    ])
    with pytest.raises(IntegrityError):
        await task_session.flush()
    await task_session.rollback()


def test_orphan_catalog_foreign_key_target_is_declared():
    foreign_keys = {
        (foreign_key.parent.name, foreign_key.target_fullname)
        for foreign_key in AgentProviderRelease.__table__.foreign_keys
    }
    assert ("catalog_release_id", "agent_catalog_releases.id") in foreign_keys


def test_real_resolver_digest_is_stable_and_persistable():
    release = build_catalog_release(get_default_tool_registry_snapshot())
    first = resolve_capabilities(release, user_id=2703, project_id="digest-project", requested_capabilities="project.context")
    second = resolve_capabilities(release, user_id=2703, project_id="digest-project", requested_capabilities="project.context")
    assert first.digest == second.digest
    assert first.snapshot_id == second.snapshot_id
    assert first.to_dict()["digest"] == first.digest
    assert len(first.digest) == 64


def _upgrade_to_020(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.upgrade(config, "020_agent_catalog_relational")


def test_fresh_020_upgrade_is_repeatable_and_creates_all_relational_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "catalog-fresh-020.sqlite"
    _upgrade_to_020(monkeypatch, db_path)
    _upgrade_to_020(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "020_agent_catalog_relational"
    tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
    assert EXPECTED_TABLES <= tables
    assert con.execute("select name from sqlite_master where type='index' and name='ix_agent_capability_executions_status'").fetchone() == ("ix_agent_capability_executions_status",)
    con.close()


def test_019_upgrade_to_020_is_repeatable_on_legacy_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "catalog-old-019.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
        INSERT INTO alembic_version VALUES ('019_agent_lease_generation');
        CREATE TABLE agent_runs (id VARCHAR(36) PRIMARY KEY);
        CREATE TABLE agent_run_steps (id VARCHAR(36) PRIMARY KEY);
        """
    )
    con.commit()
    con.close()
    _upgrade_to_020(monkeypatch, db_path)
    _upgrade_to_020(monkeypatch, db_path)
    con = sqlite3.connect(db_path)
    assert con.execute("select version_num from alembic_version").fetchone()[0] == "020_agent_catalog_relational"
    for table in EXPECTED_TABLES:
        assert con.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() == (1,)
    foreign_keys = con.execute("pragma foreign_key_list(agent_capability_executions)").fetchall()
    assert {row[2] for row in foreign_keys} >= {
        "agent_runs", "agent_run_steps", "agent_run_capability_snapshots", "agent_capability_definitions", "agent_provider_releases",
    }
    con.close()
