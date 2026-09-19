import types

import pytest
from fastapi import HTTPException

from app.services.novel_service import NovelService


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.commit_count = 0
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        return _Result(self.rows)

    async def commit(self):
        self.commit_count += 1


@pytest.mark.anyio
async def test_delete_projects_rejects_active_generation_without_partial_delete(monkeypatch):
    session = _Session([("project-1", 3, "generating")])
    service = NovelService(session)
    deleted = []

    async def fake_owner(project_id, user_id):
        return types.SimpleNamespace(id=project_id, user_id=user_id)

    async def fake_delete(project):
        deleted.append(project.id)

    monkeypatch.setattr(service, "ensure_project_owner", fake_owner)
    monkeypatch.setattr(service.repo, "delete", fake_delete)

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_projects(["project-1", "project-2"], user_id=7)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "PROJECT_HAS_ACTIVE_GENERATION"
    assert exc_info.value.detail["chapters"] == [
        {"project_id": "project-1", "chapter_number": 3, "status": "generating"}
    ]
    assert deleted == []
    assert session.commit_count == 0
    assert session.execute_count == 1