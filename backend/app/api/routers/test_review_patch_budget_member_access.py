from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import httpx
import pytest

from app.api.routers import patch_diff as patch_diff_router
from app.api.routers import review as review_router
from app.api.routers import token_budget as token_budget_router
from app.core.dependencies import get_current_user
from app.db.session import get_session
from app.main import app
from app.models import NovelProject, ProjectMember, ProjectMemberRole, User


class _NoopLLMService:
    def __init__(self, *_args, **_kwargs):
        pass

    @classmethod
    def daily_limit_scope(cls, *_args, **_kwargs):
        return nullcontext()


class _NoopService:
    def __init__(self, *_args, **_kwargs):
        pass


class _FakeSixDimensionReviewService(_NoopService):
    async def review_chapter(self, **_kwargs):
        return {"overall_score": 92, "summary": "成员编辑审查完成"}


class _FakeConsistencyService(_NoopService):
    async def check_consistency(self, **_kwargs):
        return SimpleNamespace(is_consistent=True, summary="一致", check_time_ms=1, violations=[])


class _FakePatchDiffService:
    def __init__(self, *_args, **_kwargs):
        pass

    def generate_diff(self, original_text: str, patched_text: str):
        if original_text == patched_text:
            return []
        return [
            SimpleNamespace(
                line_number=1,
                original_line=original_text,
                patched_line=patched_text,
                change_type="modified",
            )
        ]

    async def apply_patch_to_chapter(self, **_kwargs):
        return SimpleNamespace(id=701)

    async def get_patch_history(self, _chapter_id: int):
        return [SimpleNamespace(id=702)]


class _FakeTokenBudgetService:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get_budget_config(self, project_id: str):
        return {
            "project_id": project_id,
            "total_budget": 100.0,
            "chapter_budget": 5.0,
            "module_allocation": {"content": 100},
            "warning_threshold": 80.0,
        }

    async def update_budget(self, project_id: str, **kwargs):
        return SimpleNamespace(
            project_id=project_id,
            total_budget=kwargs.get("total_budget") or 100.0,
            chapter_budget=kwargs.get("chapter_budget") or 5.0,
            module_allocation=kwargs.get("module_allocation") or {"content": 100},
            warning_threshold=kwargs.get("warning_threshold") or 80.0,
        )


async def _user(session, user_id: int, username: str) -> User:
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@example.com",
        hashed_password="not-used-in-route-test",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
def http_client(task_session, monkeypatch):
    current_user = {"user": None}
    monkeypatch.setattr(review_router, "LLMService", _NoopLLMService)
    monkeypatch.setattr(review_router, "PromptService", _NoopService)
    monkeypatch.setattr(review_router, "ConstitutionService", _NoopService)
    monkeypatch.setattr(review_router, "WriterPersonaService", _NoopService)
    monkeypatch.setattr(review_router, "SixDimensionReviewService", _FakeSixDimensionReviewService)
    monkeypatch.setattr(review_router, "ConsistencyService", _FakeConsistencyService)
    monkeypatch.setattr(patch_diff_router, "PatchDiffService", _FakePatchDiffService)
    monkeypatch.setattr(token_budget_router, "TokenBudgetService", _FakeTokenBudgetService)

    async def override_session():
        yield task_session

    async def override_current_user():
        return current_user["user"]

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)

    async def request(method: str, url: str, *, user: User, **kwargs):
        current_user["user"] = SimpleNamespace(
            id=user.id,
            is_admin=bool(user.is_admin),
            is_active=bool(user.is_active),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://review-patch-budget-member-access") as client:
            return await client.request(method, url, **kwargs)

    yield request
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _project_with_members(task_session, suffix: str):
    owner = await _user(task_session, 11101, f"review-owner-{suffix}")
    viewer = await _user(task_session, 11102, f"review-viewer-{suffix}")
    editor = await _user(task_session, 11103, f"review-editor-{suffix}")
    outsider = await _user(task_session, 11104, f"review-outsider-{suffix}")
    project = NovelProject(id=f"review-patch-budget-{suffix}", user_id=owner.id, title="审查补丁预算成员权限")
    task_session.add_all(
        [
            project,
            ProjectMember(project_id=project.id, user_id=viewer.id, role=ProjectMemberRole.viewer.value),
            ProjectMember(project_id=project.id, user_id=editor.id, role=ProjectMemberRole.editor.value),
        ]
    )
    await task_session.commit()
    return viewer, editor, outsider, project


@pytest.mark.asyncio
async def test_review_routes_require_project_write_for_members(task_session, http_client):
    viewer, editor, outsider, project = await _project_with_members(task_session, "review")
    payload = {
        "project_id": project.id,
        "chapter_number": 1,
        "chapter_content": "第一章正文",
    }

    viewer_review = await http_client("POST", "/api/review/six-dimension", user=viewer, json=payload)
    assert viewer_review.status_code == 403

    outsider_review = await http_client("POST", "/api/review/six-dimension", user=outsider, json=payload)
    assert outsider_review.status_code == 403

    editor_review = await http_client("POST", "/api/review/six-dimension", user=editor, json=payload)
    assert editor_review.status_code == 200
    assert editor_review.json()["review"]["overall_score"] == 92


@pytest.mark.asyncio
async def test_patch_routes_apply_read_write_member_matrix(task_session, http_client):
    viewer, editor, outsider, project = await _project_with_members(task_session, "patch")
    diff_payload = {"original_text": "原文", "patched_text": "改文"}
    patch_payload = {"original_text": "原文", "patched_text": "改文"}
    base = f"/api/projects/{project.id}/chapters/1"

    viewer_diff = await http_client("POST", f"{base}/diff", user=viewer, json=diff_payload)
    assert viewer_diff.status_code == 200
    assert viewer_diff.json()["summary"]["modified"] == 1

    outsider_diff = await http_client("POST", f"{base}/diff", user=outsider, json=diff_payload)
    assert outsider_diff.status_code == 403

    viewer_apply = await http_client("POST", f"{base}/patch/apply", user=viewer, json=patch_payload)
    assert viewer_apply.status_code == 403

    editor_apply = await http_client("POST", f"{base}/patch/apply", user=editor, json=patch_payload)
    assert editor_apply.status_code == 201
    assert editor_apply.json()["patch_id"] == 702


@pytest.mark.asyncio
async def test_token_budget_routes_apply_read_write_member_matrix(task_session, http_client):
    viewer, editor, outsider, project = await _project_with_members(task_session, "budget")
    path = f"/api/projects/{project.id}/token-budget"

    viewer_read = await http_client("GET", path, user=viewer)
    assert viewer_read.status_code == 200
    assert viewer_read.json()["project_id"] == project.id

    outsider_read = await http_client("GET", path, user=outsider)
    assert outsider_read.status_code == 403

    viewer_write = await http_client("PUT", path, user=viewer, json={"total_budget": 210.0})
    assert viewer_write.status_code == 403

    editor_write = await http_client("PUT", path, user=editor, json={"total_budget": 210.0})
    assert editor_write.status_code == 200
    assert editor_write.json()["total_budget"] == 210.0
