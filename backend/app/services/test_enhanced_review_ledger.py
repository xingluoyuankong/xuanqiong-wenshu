"""Regression tests for enhanced review ProviderAttemptLedger propagation."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.provider_attempt import ProviderAttemptLedger
from app.services.enhanced_writing_flow import EnhancedWritingFlow
from app.services import six_dimension_review_service as six_dimension_module
from app.services import constitution_service as constitution_module
from app.services.six_dimension_review_service import SixDimensionReviewService
from app.services.constitution_service import ConstitutionService


class _FakeConstitution:
    forbidden_content = []

    def to_prompt_context(self) -> str:
        return "fixture constitution"


class _FakePromptService:
    async def get_prompt(self, name: str):
        if name == "constitution_check":
            return (
                "{{constitution}} {{chapter_number}} {{chapter_title}} "
                "{{chapter_content}}"
            )
        return None


class _FakeConstitutionService:
    async def get_constitution(self, _project_id: str):
        return _FakeConstitution()

    def get_constitution_context(self, constitution):
        return constitution.to_prompt_context() if constitution else "(none)"


class _FakePersonaService:
    async def get_active_persona(self, _project_id: str):
        return None

    def get_persona_context(self, _persona):
        return "fixture persona"


@pytest.mark.asyncio
async def test_enhanced_flow_passes_one_ledger_with_distinct_review_roles():
    flow = object.__new__(EnhancedWritingFlow)
    observed = {}

    async def review_chapter(**kwargs):
        observed["six"] = kwargs
        return {"critical_issues_count": 0, "priority_fixes": []}

    async def check_compliance(**kwargs):
        observed["constitution"] = kwargs
        return {"overall_compliance": True, "violations": []}

    async def check_style_compliance(**kwargs):
        observed["style"] = kwargs
        return {"compliance": True, "issues": []}

    flow.review_service = SimpleNamespace(review_chapter=review_chapter)
    flow.constitution_service = SimpleNamespace(check_compliance=check_compliance)
    flow.writer_persona_service = SimpleNamespace(check_style_compliance=check_style_compliance)

    ledger = ProviderAttemptLedger(run_id="enhanced-review-run", max_attempts=12)
    result = await flow.post_generation_review(
        "project-1",
        3,
        "第三章",
        "正文",
        attempt_ledger=ledger,
    )

    assert result["overall_passed"] is True
    assert observed["six"]["attempt_ledger"] is ledger
    assert observed["six"]["attempt_role"] == "six_dimension_review"
    assert observed["constitution"]["attempt_ledger"] is ledger
    assert observed["constitution"]["attempt_role"] == "constitution_check"
    assert "attempt_ledger" not in observed["style"]


@pytest.mark.asyncio
async def test_six_dimension_policy_uses_optional_shared_ledger(monkeypatch):
    observed = {}

    async def fake_call_generation_json(**kwargs):
        observed["policy"] = kwargs["policy"]
        return SimpleNamespace(data={"overall_score": 91, "summary": "通过"})

    monkeypatch.setattr(six_dimension_module, "call_generation_json", fake_call_generation_json)
    service = SixDimensionReviewService(
        db=None,
        llm_service=object(),
        prompt_service=_FakePromptService(),
        constitution_service=_FakeConstitutionService(),
        writer_persona_service=_FakePersonaService(),
    )
    ledger = ProviderAttemptLedger(run_id="six-review-run", max_attempts=8)

    result = await service.review_chapter(
        "project-1",
        1,
        "第一章",
        "正文",
        attempt_ledger=ledger,
    )

    assert result["overall_score"] == 91
    assert observed["policy"].attempt_ledger is ledger
    assert observed["policy"].attempt_role == "six_dimension_review"


@pytest.mark.asyncio
async def test_constitution_policy_uses_optional_shared_ledger(monkeypatch):
    observed = {}

    async def fake_call_generation_json(**kwargs):
        observed["policy"] = kwargs["policy"]
        return SimpleNamespace(data={"overall_compliance": True, "violations": []})

    class _Db:
        async def execute(self, _query):
            return SimpleNamespace(scalar_one_or_none=lambda: _FakeConstitution())

    monkeypatch.setattr(constitution_module, "call_generation_json", fake_call_generation_json)
    service = ConstitutionService(
        db=_Db(),
        llm_service=object(),
        prompt_service=_FakePromptService(),
    )
    ledger = ProviderAttemptLedger(run_id="constitution-run", max_attempts=8)

    result = await service.check_compliance(
        "project-1",
        1,
        "第一章",
        "正文",
        attempt_ledger=ledger,
    )

    assert result["overall_compliance"] is True
    assert observed["policy"].attempt_ledger is ledger
    assert observed["policy"].attempt_role == "constitution_check"


@pytest.mark.asyncio
async def test_review_services_keep_legacy_calls_without_ledger(monkeypatch):
    six_observed = {}
    constitution_observed = {}

    async def fake_six(**kwargs):
        six_observed["policy"] = kwargs["policy"]
        return SimpleNamespace(data={"overall_score": 88})

    async def fake_constitution(**kwargs):
        constitution_observed["policy"] = kwargs["policy"]
        return SimpleNamespace(data={"overall_compliance": True, "violations": []})

    monkeypatch.setattr(six_dimension_module, "call_generation_json", fake_six)
    six_service = SixDimensionReviewService(
        None,
        object(),
        _FakePromptService(),
        _FakeConstitutionService(),
        _FakePersonaService(),
    )
    six_result = await six_service.review_chapter("p", 1, "t", "c")

    class _Db:
        async def execute(self, _query):
            return SimpleNamespace(scalar_one_or_none=lambda: _FakeConstitution())

    monkeypatch.setattr(constitution_module, "call_generation_json", fake_constitution)
    constitution_service = ConstitutionService(_Db(), object(), _FakePromptService())
    constitution_result = await constitution_service.check_compliance("p", 1, "t", "c")

    assert six_result["overall_score"] == 88
    assert six_observed["policy"].attempt_ledger is None
    assert six_observed["policy"].attempt_role == "six_dimension_review"
    assert constitution_result["overall_compliance"] is True
    assert constitution_observed["policy"].attempt_ledger is None
    assert constitution_observed["policy"].attempt_role == "constitution_check"
