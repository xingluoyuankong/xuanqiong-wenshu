import pytest

from app.services.pipeline_orchestrator import PipelineConfig, PipelineOrchestrator


def test_t25_long_tier_does_not_repeat_whole_chapter_in_stable_mode():
    long_tier = PipelineConfig(preset="enhanced", target_word_count=7000, version_count=1)
    assert PipelineOrchestrator._build_stable_retry_config(long_tier) is None


def test_t25_sabotage_restoring_old_ten_thousand_boundary_fails_long_tier_contract(monkeypatch):
    def old_boundary(config):
        if config.preset == "stable" or config.target_word_count < 2500 or config.target_word_count >= 10000:
            return None
        fallback = PipelineConfig(**vars(config))
        fallback.preset = "stable"
        fallback.version_count = 1
        return fallback

    monkeypatch.setattr(PipelineOrchestrator, "_build_stable_retry_config", staticmethod(old_boundary))
    with pytest.raises(AssertionError):
        assert PipelineOrchestrator._build_stable_retry_config(
            PipelineConfig(preset="enhanced", target_word_count=7000, version_count=1)
        ) is None
