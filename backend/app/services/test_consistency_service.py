import pytest
from types import SimpleNamespace
import inspect

from app.agent.provider_attempt import ProviderAttemptLedger
from app.services import consistency_service as consistency_module
from app.services.consistency_service import (
    ConsistencyCheckResult,
    ConsistencyService,
    ConsistencyViolation,
    ViolationSeverity,
)


def _service(monkeypatch):
    service = ConsistencyService(db=object(), llm_service=object())

    async def fake_context(*args, **kwargs):
        return {
            "novel_setting": "设定",
            "character_state": "角色状态",
            "global_summary": "前文摘要",
            "plot_arcs": "剧情线",
        }

    monkeypatch.setattr(service, "_get_check_context", fake_context)
    return service


def _violation(location="第2段"):
    return ConsistencyViolation(
        severity=ViolationSeverity.CRITICAL,
        category="plot",
        description="需要修复的承接冲突",
        location=location,
        suggested_fix="修复承接",
    )


def test_violation_severity_values():
    assert ViolationSeverity.CRITICAL == "critical"
    assert ViolationSeverity.MAJOR == "major"
    assert ViolationSeverity.MINOR == "minor"


def test_consistency_check_result_fields():
    r = ConsistencyCheckResult(
        is_consistent=True,
        violations=[],
        summary="No issues found",
        check_time_ms=120,
        status="passed",
    )
    assert r.is_consistent is True
    assert r.summary == "No issues found"
    assert r.status == "passed"
    assert r.check_time_ms == 120


def test_consistency_violation_fields():
    v = ConsistencyViolation(
        severity=ViolationSeverity.MAJOR,
        category="plot",
        description="Missing hook at chapter end",
        location="chapter 5 ending",
        suggested_fix="Add cliffhanger",
        confidence=0.85,
    )
    assert v.severity == ViolationSeverity.MAJOR
    assert v.category == "plot"
    assert v.description == "Missing hook at chapter end"
    assert v.confidence == 0.85


def test_consistency_ledger_parameters_are_optional_keyword_only():
    for name in ("check_consistency", "auto_fix", "check_and_fix"):
        parameter = inspect.signature(getattr(ConsistencyService, name)).parameters["attempt_ledger"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is None

    local_parameter = inspect.signature(ConsistencyService._auto_fix_locally).parameters["attempt_ledger"]
    assert local_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert local_parameter.default is None


@pytest.mark.asyncio
async def test_check_consistency_passes_shared_ledger_and_role(monkeypatch):
    service = _service(monkeypatch)
    ledger = ProviderAttemptLedger(run_id="consistency-test", max_attempts=8)
    captured = {}

    async def fake_json(**kwargs):
        captured["policy"] = kwargs["policy"]
        return SimpleNamespace(
            data={"is_consistent": True, "violations": [], "summary": "通过"},
            provider_attempts={"provider_attempts": []},
        )

    monkeypatch.setattr(consistency_module, "call_generation_json", fake_json)

    result = await service.check_consistency(
        project_id="project-1",
        chapter_text="章节正文",
        user_id=7,
        attempt_ledger=ledger,
        attempt_role="continuity_audit",
    )

    assert result.is_consistent is True
    assert captured["policy"].attempt_ledger is ledger
    assert captured["policy"].attempt_role == "continuity_audit"


@pytest.mark.asyncio
async def test_check_consistency_legacy_call_keeps_default_ledger_behavior(monkeypatch):
    service = _service(monkeypatch)
    captured = {}

    async def fake_json(**kwargs):
        captured["policy"] = kwargs["policy"]
        return SimpleNamespace(
            data={"is_consistent": True, "violations": [], "summary": "通过"},
            provider_attempts={"provider_attempts": []},
        )

    monkeypatch.setattr(consistency_module, "call_generation_json", fake_json)

    result = await service.check_consistency("project-1", "章节正文", 7)

    assert result.is_consistent is True
    assert captured["policy"].attempt_ledger is None
    assert captured["policy"].attempt_role == "consistency_check"


@pytest.mark.asyncio
async def test_auto_fix_local_patch_uses_shared_ledger_and_local_role(monkeypatch):
    service = _service(monkeypatch)
    ledger = ProviderAttemptLedger(run_id="consistency-local", max_attempts=8)
    captured = {}

    async def fake_text(**kwargs):
        captured["policy"] = kwargs["policy"]
        return SimpleNamespace(text="局部修复后的正文")

    monkeypatch.setattr(consistency_module, "call_generation_text", fake_text)

    chapter = "第一段原文内容\n\n第二段存在冲突\n\n第三段原文内容"
    fixed = await service._auto_fix_locally(
        chapter_text=chapter,
        violations=[_violation()],
        context={"novel_setting": "", "character_state": "", "global_summary": ""},
        user_id=7,
        attempt_ledger=ledger,
        attempt_role="consistency_repair_local",
    )

    assert fixed == "局部修复后的正文"
    assert captured["policy"].attempt_ledger is ledger
    assert captured["policy"].attempt_role == "consistency_repair_local"


@pytest.mark.asyncio
async def test_auto_fix_fallback_uses_same_ledger_and_distinct_fallback_role(monkeypatch):
    service = _service(monkeypatch)
    ledger = ProviderAttemptLedger(run_id="consistency-fallback", max_attempts=8)
    captured = {}

    async def fake_local(**kwargs):
        captured["local_ledger"] = kwargs["attempt_ledger"]
        captured["local_role"] = kwargs["attempt_role"]
        return None

    async def fake_text(**kwargs):
        captured["fallback_policy"] = kwargs["policy"]
        return SimpleNamespace(text="第一段原文内容\n\n第二段修复内容\n\n第三段原文内容")

    monkeypatch.setattr(service, "_auto_fix_locally", fake_local)
    monkeypatch.setattr(consistency_module, "call_generation_text", fake_text)

    result = await service.auto_fix(
        project_id="project-1",
        chapter_text="第一段原文内容\n\n第二段存在冲突\n\n第三段原文内容",
        violations=[_violation()],
        user_id=7,
        allow_full_chapter_fallback=True,
        attempt_ledger=ledger,
        attempt_role="consistency_repair",
    )

    assert result == "第一段原文内容\n\n第二段修复内容\n\n第三段原文内容"
    assert captured["local_ledger"] is ledger
    assert captured["fallback_policy"].attempt_ledger is ledger
    assert captured["local_role"] == "consistency_repair_local"
    assert captured["fallback_policy"].attempt_role == "consistency_repair_fallback"


@pytest.mark.asyncio
async def test_check_and_fix_forwards_one_ledger_with_distinct_check_and_repair_roles(monkeypatch):
    service = _service(monkeypatch)
    ledger = ProviderAttemptLedger(run_id="consistency-combined", max_attempts=8)
    captured = {}

    async def fake_check(**kwargs):
        captured["check"] = kwargs
        return ConsistencyCheckResult(
            is_consistent=False,
            violations=[_violation()],
            summary="发现冲突",
        )

    async def fake_fix(**kwargs):
        captured["fix"] = kwargs
        return "修复后的章节"

    monkeypatch.setattr(service, "check_consistency", fake_check)
    monkeypatch.setattr(service, "auto_fix", fake_fix)

    result = await service.check_and_fix(
        project_id="project-1",
        chapter_text="章节正文",
        user_id=7,
        attempt_ledger=ledger,
        attempt_role="consistency_pipeline",
    )

    assert result["fixed_content"] == "修复后的章节"
    assert captured["check"]["attempt_ledger"] is ledger
    assert captured["fix"]["attempt_ledger"] is ledger
    assert captured["check"]["attempt_role"] == "consistency_pipeline_check"
    assert captured["fix"]["attempt_role"] == "consistency_pipeline_repair"
