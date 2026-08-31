from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.services import project_ledger_lease_service as leases


@pytest.fixture
async def ledger_factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(leases, "AsyncSessionLocal", factory)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_project_ledger_lease_is_exclusive_and_releasable(ledger_factory):
    token, active = await leases.acquire_project_ledger_lease(
        project_id="project-1", chapter_number=3, selected_version_id=8
    )
    assert token
    assert active is None

    duplicate, active = await leases.acquire_project_ledger_lease(
        project_id="project-1", chapter_number=4
    )
    assert duplicate is None
    assert active is not None
    assert active["chapter_number"] == 3
    assert active["selected_version_id"] == 8

    await leases.release_project_ledger_lease(project_id="project-1", lease_token=token)
    replacement, active = await leases.acquire_project_ledger_lease(
        project_id="project-1", chapter_number=4
    )
    assert replacement
    assert replacement != token
    assert active is None


@pytest.mark.asyncio
async def test_project_ledger_context_releases_after_exit(ledger_factory):
    async with leases.project_ledger_lease("project-2", wait_seconds=0.2) as token:
        assert token
        duplicate, active = await leases.acquire_project_ledger_lease(project_id="project-2")
        assert duplicate is None
        assert active is not None

    replacement, active = await leases.acquire_project_ledger_lease(project_id="project-2")
    assert replacement
    assert active is None


@pytest.mark.asyncio
async def test_project_ledger_lease_file_database_allows_only_one_concurrent_owner(tmp_path, monkeypatch):
    db_path = tmp_path / "lease-race.sqlite"
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(leases, "AsyncSessionLocal", factory)

    results = await asyncio.gather(
        *(leases.acquire_project_ledger_lease(project_id="race-project") for _ in range(20))
    )
    acquired = [token for token, _active in results if token is not None]
    blocked = [active for _token, active in results if active is not None]
    assert len(acquired) == 1
    assert len(blocked) == 19

    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_project_ledger_lease_is_taken_over_once(ledger_factory):
    old_token, _ = await leases.acquire_project_ledger_lease(project_id="expired-project")
    async with ledger_factory() as session:
        from sqlalchemy import update
        from app.models.novel import ProjectLedgerSyncLease

        await session.execute(
            update(ProjectLedgerSyncLease)
            .where(ProjectLedgerSyncLease.project_id == "expired-project")
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await session.commit()

    results = await asyncio.gather(
        *(leases.acquire_project_ledger_lease(project_id="expired-project") for _ in range(10))
    )
    acquired = [token for token, _active in results if token is not None]
    assert len(acquired) == 1
    assert acquired[0] != old_token
    assert sum(1 for _token, active in results if active is not None) == 9
