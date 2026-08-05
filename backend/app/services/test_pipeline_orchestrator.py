"""Tests for PipelineOrchestrator quality gates and version config."""
import pytest
import asyncio


class TestVersionCount:
    def test_default_is_3(self):
        from app.services.pipeline_orchestrator import DEFAULT_GENERATED_VERSION_COUNT
        assert DEFAULT_GENERATED_VERSION_COUNT == 3

    def test_max_is_4(self):
        from app.services.pipeline_orchestrator import MAX_GENERATED_VERSION_COUNT
        assert MAX_GENERATED_VERSION_COUNT == 4


class TestQualityGate:
    def test_score_43_passes(self):
        from app.services.pipeline_orchestrator import PipelineOrchestrator
        gate = PipelineOrchestrator._build_structural_quality_gate({
            "self_critique": {"final_score": 43, "critical_count": 0, "major_count": 5},
        })
        blockers = gate.get("blockers", [])
        score_blockers = [b for b in blockers if "score" in str(b.get("code","")).lower()]
        assert len(score_blockers) == 0

    def test_score_40_blocked(self):
        from app.services.pipeline_orchestrator import PipelineOrchestrator
        gate = PipelineOrchestrator._build_structural_quality_gate({
            "self_critique": {"final_score": 40, "critical_count": 0, "major_count": 5},
        })
        blockers = gate.get("blockers", [])
        assert len(blockers) >= 1


class TestSelfCritiqueConfig:

    def test_absolute_max_iterations(self):
        from app.services.self_critique_service import SelfCritiqueService
        assert SelfCritiqueService.ABSOLUTE_MAX_ITERATIONS == 2

    def test_target_score_default_is_60(self):
        import inspect
        from app.services.self_critique_service import SelfCritiqueService
        sig = inspect.signature(SelfCritiqueService.critique_and_revise_loop)
        target = sig.parameters.get("target_score")
        assert target is not None
        assert target.default == 60.0


class TestOutlineGen:

    def test_default_volumes_is_8(self):
        import inspect
        from app.services.long_novel_outline_generator import LongNovelOutlineGenerator
        sig = inspect.signature(LongNovelOutlineGenerator.generate_outline)
        vol = sig.parameters.get("volume_count")
        assert vol is not None
        assert vol.default == 8

    def test_estimate_long_novel(self):
        from app.services.long_novel_outline_generator import LongNovelOutlineGenerator
        s = LongNovelOutlineGenerator.estimate_structure(500000)
        assert s["volume_count"] >= 5
        assert s["chapters_per_volume"] >= 15
        assert s["total_chapters"] >= 100


class TestConfigSyncManager:

    @pytest.mark.asyncio
    async def test_bump_increments(self):
        from app.services.config_sync_manager import ConfigSyncManager
        mgr = ConfigSyncManager()
        uid = 99999
        assert await mgr.get_version(uid) == 0
        assert await mgr.bump_version(uid) == 1
        assert await mgr.get_version(uid) == 1

    @pytest.mark.asyncio
    async def test_subscribe_receives(self):
        from app.services.config_sync_manager import ConfigSyncManager
        mgr = ConfigSyncManager()
        uid = 88888
        q = await mgr.subscribe(uid)
        try:
            await mgr.bump_version(uid)
            event = await asyncio.wait_for(q.get(), timeout=1.0)
            assert event["version"] == 1
        finally:
            await mgr.unsubscribe(uid, q)