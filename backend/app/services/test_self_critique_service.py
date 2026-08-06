"""Tests for self_critique_service — verify ABSOLUTE_MAX_ITERATIONS guard."""
import pytest
from unittest.mock import AsyncMock
from app.services.self_critique_service import SelfCritiqueService, CritiqueDimension


@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_llm():
    return AsyncMock()

@pytest.fixture
def mock_prompt():
    return AsyncMock()

@pytest.fixture
def svc(mock_db, mock_llm, mock_prompt):
    return SelfCritiqueService(db=mock_db, llm_service=mock_llm, prompt_service=mock_prompt)


class TestSelfCritiqueService:

    def test_absolute_max_iterations_constant(self, svc):
        assert svc.ABSOLUTE_MAX_ITERATIONS == 2

    def test_critique_dimensions_complete(self):
        dims = list(CritiqueDimension)
        assert len(dims) >= 8
        names = {d.value for d in dims}
        for r in {"logic", "continuity", "pov", "character", "writing", "pacing"}:
            assert r in names, f"Missing: {r}"

    @pytest.mark.asyncio
    async def test_full_critique_returns_dict(self, svc):
        svc._critique_llm_call = AsyncMock(return_value='{"overall_score": 70, "issues": []}')
        result = await svc.full_critique("Test. " * 300, user_id=0)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_critique_and_revise_loop_handles_iteration_limit(self, svc):
        crit = {
            "overall_score": 35, "weighted_score": 35,
            "critical_count": 0, "major_count": 0, "minor_count": 0,
            "needs_revision": True, "priority_fixes": [],
            "dimensions": {}, "issues": [],
        }
        svc.full_critique = AsyncMock(return_value=crit)
        svc._revise_chapter_stagewide = AsyncMock(return_value="revised " * 100)
        svc.quick_critique = AsyncMock(return_value=crit)

        try:
            result = await svc.critique_and_revise_loop(
                chapter_content="Test. " * 500,
                target_score=70,
                user_id=0,
                max_iterations=svc.ABSOLUTE_MAX_ITERATIONS,
            )
            assert result is not None
        except Exception as e:
            pytest.fail(f"No crash: {e}")
