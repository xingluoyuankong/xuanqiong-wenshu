from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.api.routers import knowledge_graph
from app.schemas.user import UserInDB


import pytest
@pytest.fixture
def anyio_backend():
    return "asyncio"


class _OwnerService:
    def __init__(self, _session):
        pass

    async def ensure_project_owner(self, _project_id, _user_id):
        return object()


class _PlotThread:
    def __init__(self, thread_id="t1", title="主线"):
        self.thread_id = thread_id
        self.title = title

    def to_dict(self):
        return {
            "thread_id": self.thread_id,
            "title": self.title,
            "characters": ["林七"],
            "events": [{"description": "废桥对峙"}],
            "chapter_range": (1, 3),
            "key_events": ["废桥对峙"],
        }


class _KnowledgeGraphService:
    last_sync_calls = 0
    last_graph_calls = 0
    last_thread_calls = 0

    def __init__(self, _session):
        pass

    async def sync_from_story_memory(self, project_id):
        _KnowledgeGraphService.last_sync_calls += 1
        return {"created_nodes": 1, "created_edges": 1, "removed_nodes": 0, "removed_edges": 0}

    async def get_project_graph(self, project_id):
        _KnowledgeGraphService.last_graph_calls += 1
        return {
            "project_id": project_id,
            "nodes": [
                {
                    "id": 1,
                    "project_id": project_id,
                    "name": "林七",
                    "role_type": "protagonist",
                    "description": "主角",
                    "traits": [],
                    "goals": [],
                    "fears": [],
                    "background": None,
                    "status": "alive",
                    "location": None,
                    "emotional_state": None,
                    "blueprint_character_id": 9,
                    "extra": None,
                    "fact_source": "blueprint_character",
                    "fact_source_label": "蓝图角色",
                    "first_chapter": 1,
                    "latest_chapter": 3,
                    "confidence": 90,
                    "lifecycle": "active",
                    "relationship_count": 1,
                    "created_at": "2026-07-20T00:00:00",
                    "updated_at": "2026-07-20T00:00:00",
                }
            ],
            "edges": [
                {
                    "id": 2,
                    "source_id": 1,
                    "target_id": 1,
                    "source_name": "林七",
                    "target_name": "林七",
                    "event_type": "conflict",
                    "description": "废桥对峙",
                    "chapter_number": 1,
                    "scene_number": 1,
                    "timestamp": None,
                    "order_index": 0,
                    "causality": "cause",
                    "importance": 8,
                    "emotional_impact": None,
                    "plot_advancement": None,
                    "extra": None,
                    "fact_source": "timeline_event",
                    "fact_source_label": "时间线事件",
                    "source_chapter": 1,
                    "latest_chapter": 1,
                    "confidence": 80,
                    "created_at": "2026-07-20T00:00:00",
                    "updated_at": "2026-07-20T00:00:00",
                }
            ],
            "node_count": 1,
            "edge_count": 1,
        }

    async def _analyze_project_threads(self, project_id):
        _KnowledgeGraphService.last_thread_calls += 1
        return [_PlotThread()]


@asynccontextmanager
async def _fake_project_ledger_lease(project_id, **_kwargs):
    _fake_project_ledger_lease.calls = getattr(_fake_project_ledger_lease, "calls", 0) + 1
    _fake_project_ledger_lease.last_project_id = project_id
    yield "lease-token"


@pytest.mark.asyncio
async def test_knowledge_graph_overview_syncs_once_and_returns_graph_plus_threads(monkeypatch):
    _KnowledgeGraphService.last_sync_calls = 0
    _KnowledgeGraphService.last_graph_calls = 0
    _KnowledgeGraphService.last_thread_calls = 0
    _fake_project_ledger_lease.calls = 0

    monkeypatch.setattr(knowledge_graph, "NovelService", _OwnerService)
    monkeypatch.setattr(knowledge_graph, "KnowledgeGraphService", _KnowledgeGraphService)
    monkeypatch.setattr(knowledge_graph, "project_ledger_lease", _fake_project_ledger_lease)
    user = UserInDB(id=7, username="owner", email=None, hashed_password="x")

    payload = await knowledge_graph.get_knowledge_graph_overview(
        "project-1",
        session=object(),
        current_user=user,
    )

    assert payload["project_id"] == "project-1"
    assert payload["graph"]["node_count"] == 1
    assert payload["graph"]["edge_count"] == 1
    assert payload["graph"]["nodes"][0]["name"] == "林七"
    assert payload["thread_count"] == 1
    assert payload["threads"][0]["title"] == "主线"
    assert payload["sync"]["created_nodes"] == 1
    assert _KnowledgeGraphService.last_sync_calls == 1
    assert _KnowledgeGraphService.last_graph_calls == 1
    assert _KnowledgeGraphService.last_thread_calls == 1
    assert _fake_project_ledger_lease.calls == 1
    assert _fake_project_ledger_lease.last_project_id == "project-1"
