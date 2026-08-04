import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.novel import ProjectLedgerSyncLease
from app.models.user import User
from app.models.novel import NovelProject
from app.services import project_ledger_lease_service as lease_service


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_project_ledger_lease_serializes_and_allows_null_selected_version(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ledger-lease.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Point lease service session factory at temp DB.
    monkeypatch.setattr(lease_service, "AsyncSessionLocal", session_factory)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="t@example.com", hashed_password="h"))
            session.add(NovelProject(id="p-lease", user_id=1, title="Lease", initial_prompt="x", status="draft"))
            await session.commit()

        token_a, active = await lease_service.acquire_project_ledger_lease(
            project_id="p-lease",
            chapter_number=0,
            selected_version_id=None,
        )
        assert token_a is not None
        assert active is None

        token_b, active_b = await lease_service.acquire_project_ledger_lease(
            project_id="p-lease",
            chapter_number=12,
            selected_version_id=99,
        )
        assert token_b is None
        assert active_b is not None
        assert active_b["chapter_number"] == 0
        assert active_b["selected_version_id"] is None

        await lease_service.release_project_ledger_lease(project_id="p-lease", lease_token=token_a)

        token_c, active_c = await lease_service.acquire_project_ledger_lease(
            project_id="p-lease",
            chapter_number=12,
            selected_version_id=99,
        )
        assert token_c is not None
        assert active_c is None
        await lease_service.release_project_ledger_lease(project_id="p-lease", lease_token=token_c)
    finally:
        await engine.dispose()
