from fastapi import BackgroundTasks, Response
import pytest

from app.api.routers import novels
from app.schemas.novel import BlueprintGenerationJobResponse
from app.schemas.user import UserInDB


@pytest.mark.asyncio
async def test_legacy_blueprint_route_forwards_to_background_job(monkeypatch):
    captured = {}

    async def fake_start_blueprint_generation(**kwargs):
        captured.update(kwargs)
        return BlueprintGenerationJobResponse(
            run_id="run-1",
            project_id=kwargs["project_id"],
            status="queued",
            progress_stage="queued",
            progress_message="蓝图生成任务已入队",
        )

    monkeypatch.setattr(novels, "start_blueprint_generation", fake_start_blueprint_generation)

    response = Response()
    background_tasks = BackgroundTasks()
    current_user = UserInDB(id=7, username="tester", email=None, hashed_password="x")
    payload = {"force_stage": "chapter_outline"}

    result = await novels.generate_blueprint(
        project_id="project-1",
        response=response,
        background_tasks=background_tasks,
        payload=payload,
        session=object(),
        current_user=current_user,
    )

    assert result.status == "queued"
    assert result.project_id == "project-1"
    assert response.headers["Deprecation"] == "true"
    assert response.headers["X-Xuanqiong-Legacy-Route"] == "blueprint-generate-sync"
    assert "blueprint/generate/start" in response.headers["Link"]
    assert captured["background_tasks"] is background_tasks
    assert captured["payload"] is payload
    assert captured["current_user"] is current_user
