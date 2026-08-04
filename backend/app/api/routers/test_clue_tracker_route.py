from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.api.routers import clue_tracker
from app.schemas.user import UserInDB


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _OwnerService:
    def __init__(self, _session):
        pass

    async def ensure_project_owner(self, _project_id, _user_id):
        return object()


class _ClueTrackerService:
    def __init__(self, _session):
        self.sync_calls = 0

    async def sync_from_foreshadowings(self, project_id, *, commit=True):
        self.sync_calls += 1
        _ClueTrackerService.last_sync_calls = getattr(_ClueTrackerService, "last_sync_calls", 0) + 1
        return {"created": 1, "updated": 0, "removed": 0, "links_created": 1, "links_reused": 0}

    async def get_project_clues(self, project_id, status=None, clue_type=None, include_red_herring=True):
        return [
            SimpleNamespace(
                id=11,
                project_id=project_id,
                name="Salt-code ledger",
                clue_type="key_evidence",
                description="Hidden salt-code",
                importance=5,
                planted_chapter=1,
                resolution_chapter=None,
                status="active",
                is_red_herring=False,
                red_herring_explanation=None,
                clue_content="code",
                hint_level=2,
                design_intent="payoff later",
                created_at=SimpleNamespace(isoformat=lambda: "2026-07-20T00:00:00"),
                updated_at=SimpleNamespace(isoformat=lambda: "2026-07-20T00:00:00"),
            )
        ]

    async def analyze_clue_threads(self, project_id):
        return {
            "project_id": project_id,
            "total_clues": 1,
            "type_counts": {"key_evidence": 1},
            "status_counts": {"active": 1},
            "red_herring_count": 0,
            "unresolved_count": 1,
            "threads": [{"thread_type": "key_evidence", "clue_count": 1, "clue_ids": [11]}],
        }


@asynccontextmanager
async def _fake_project_ledger_lease(project_id, **_kwargs):
    _fake_project_ledger_lease.calls = getattr(_fake_project_ledger_lease, "calls", 0) + 1
    _fake_project_ledger_lease.last_project_id = project_id
    yield "lease-token"


@pytest.mark.anyio
async def test_clue_overview_syncs_once_and_returns_list_plus_analysis(monkeypatch):
    _ClueTrackerService.last_sync_calls = 0
    _fake_project_ledger_lease.calls = 0
    instances = []

    def factory(session):
        service = _ClueTrackerService(session)
        instances.append(service)
        return service

    monkeypatch.setattr(clue_tracker, "NovelService", _OwnerService)
    monkeypatch.setattr(clue_tracker, "ClueTrackerService", factory)
    monkeypatch.setattr(clue_tracker, "project_ledger_lease", _fake_project_ledger_lease)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    payload = await clue_tracker.get_clue_overview(
        "project-1",
        status=None,
        clue_type=None,
        include_red_herring=True,
        session=object(),
        current_user=user,
    )

    assert payload["project_id"] == "project-1"
    assert len(payload["clues"]) == 1
    assert payload["clues"][0]["name"] == "Salt-code ledger"
    assert payload["analysis"]["total_clues"] == 1
    assert payload["analysis"]["unresolved_count"] == 1
    assert payload["sync"]["created"] == 1
    assert _ClueTrackerService.last_sync_calls == 1
    assert _fake_project_ledger_lease.calls == 1
    assert _fake_project_ledger_lease.last_project_id == "project-1"
    assert len(instances) == 1
