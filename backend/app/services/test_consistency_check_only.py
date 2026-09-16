from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.consistency_service import ConsistencyService, ViolationSeverity
from app.services.pipeline_orchestrator import PipelineOrchestrator


class _Session:
    pass


@pytest.mark.asyncio
async def test_consistency_check_only_never_runs_auto_fix(monkeypatch):
    calls = {"check": 0, "auto_fix": 0}
    violation = SimpleNamespace(
        severity=ViolationSeverity.MAJOR,
        category="plot",
        description="复检仍有冲突",
        location="第2段",
        suggested_fix="保留当前局部修订结果，交由后续人工处理。",
        confidence=0.9,
    )

    async def check(self, project_id, chapter_text, user_id, include_foreshadowing=True, **_kwargs):
        calls["check"] += 1
        return SimpleNamespace(
            is_consistent=False,
            status="warning",
            summary="复检完成",
            check_time_ms=3,
            violations=[violation],
        )

    async def auto_fix(self, *args, **kwargs):
        calls["auto_fix"] += 1
        return "不应被调用"

    monkeypatch.setattr(ConsistencyService, "check_consistency", check)
    monkeypatch.setattr(ConsistencyService, "auto_fix", auto_fix)
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator.session = _Session()
    orchestrator.llm_service = AsyncMock()

    content, report = await orchestrator._run_consistency_check(
        project_id="project-1", chapter_text="局部修订正文", user_id=1, mode="check_only"
    )

    assert content == "局部修订正文"
    assert report["mode"] == "check_only"
    assert report["auto_fix_applied"] is False
    assert report["auto_fix_accepted"] is False
    assert calls == {"check": 1, "auto_fix": 0}

