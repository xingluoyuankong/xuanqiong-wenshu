from fastapi import HTTPException
import pytest

from app.services.foreshadowing_tracker_service import ForeshadowingTrackerService
from app.services.pipeline_orchestrator import PipelineOrchestrator


class _PromptService:
    async def get_prompt(self, name: str):
        assert name == "foreshadowing_reminder"
        return "{{chapter_number}}\n{{chapter_outline}}\n{{active_foreshadowings}}"


class _RetryThenSuccessLLM:
    def __init__(self):
        self.calls = []

    async def get_llm_response(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise HTTPException(status_code=503, detail={"retryable": True, "message": "provider jitter"})
        return '{"foreshadowings_to_develop":[{"name":"潮印裂纹","urgency":"high","reason":"已接近回收窗口","suggested_development":"让裂纹在关键证据上再次响应。"}]}'


@pytest.mark.anyio
async def test_foreshadowing_reminder_reports_provider_jitter_to_runtime_callback():
    service = ForeshadowingTrackerService(None, _RetryThenSuccessLLM(), _PromptService())

    async def fake_get_foreshadowings_for_chapter(project_id: str, chapter_number: int):
        return {"urgent": [], "due_soon": [], "overdue": [], "related": []}

    service.get_foreshadowings_for_chapter = fake_get_foreshadowings_for_chapter
    events = []

    async def progress_callback(stage: str, message: str):
        events.append((stage, message))

    result = await service.get_foreshadowing_reminders(
        project_id="project-1",
        chapter_number=7,
        chapter_outline="证据被拆散后，众人必须分头逃生。",
        user_id=1,
        progress_callback=progress_callback,
    )

    assert result["foreshadowings_to_develop"][0]["name"] == "潮印裂纹"
    assert events == [("foreshadowing_chapter_task", "伏笔账本-章节提醒遇到上游抖动，正在进行第 1/1 次重试")]


def test_enhanced_context_progress_stages_have_user_visible_progress_slots():
    assert PipelineOrchestrator._infer_stage_progress_percent("enhanced_context") == 18
    assert PipelineOrchestrator._infer_stage_progress_percent("foreshadowing_chapter_task") == 19
