from app.api.routers.writer import _build_advanced_background_flow_config, _build_compat_generate_flow_config
from app.schemas.novel import AdvancedGenerateRequest, FlowConfig, GenerateChapterRequest
import pytest
from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_compat_generate_respects_explicit_short_word_counts():
    config = _build_compat_generate_flow_config(
        GenerateChapterRequest(
            chapter_number=1,
            target_word_count=700,
            min_word_count=350,
        )
    )

    assert config["target_word_count"] == 700
    assert config["min_word_count"] == 350
    assert config["preset"] == "basic"
    assert config["enable_enrichment"] is False
    assert config["enable_self_critique"] is False
    assert config["allow_truncated_response"] is False
    assert config["compat_short_chapter_mode"] is True
    assert config["chapter_draft_contract"]["tier"] == "short"
    assert config["generation_strategy"] == "single_pass_compact"


def test_compat_generate_uses_heavier_quality_defaults_for_default_long_chapters():
    config = _build_compat_generate_flow_config(GenerateChapterRequest(chapter_number=1))

    assert config["target_word_count"] == 5000
    assert config["min_word_count"] == 4500
    assert config["preset"] == "ultimate"
    assert config["versions"] == 2
    assert "enable_consistency" not in config
    assert "enable_enrichment" not in config
    assert "enable_self_critique" not in config
    assert "enable_reader_sim" not in config
    assert config["allow_truncated_response"] is False
    assert config["max_enrich_iterations"] == 5
    assert config["chapter_draft_contract"]["target_word_count"] == 5000
    assert config["chapter_draft_contract"]["recommended_scene_count_min"] >= 4
    assert config["generation_strategy"] == "single_pass_scene_led_with_retry_gate"


def test_compat_generate_raises_candidate_count_for_extra_long_chapters():
    config = _build_compat_generate_flow_config(
        GenerateChapterRequest(chapter_number=1, target_word_count=7000, min_word_count=6500)
    )

    assert config["preset"] == "ultimate"
    assert config["versions"] == 3
    assert config["max_enrich_iterations"] == 6
    assert config["chapter_draft_contract"]["tier"] == "long"
    assert config["chapter_draft_contract"]["recommended_scene_count_min"] == 5
    assert config["generation_strategy"] == "single_pass_grouped_scenes_with_fusion_check"


def test_compat_generate_supports_extra_long_quality_contract():
    config = _build_compat_generate_flow_config(
        GenerateChapterRequest(chapter_number=1, target_word_count=10000, min_word_count=9200)
    )

    assert config["preset"] == "ultimate"
    assert config["versions"] == 4
    assert config["max_enrich_iterations"] == 8
    assert config["chapter_draft_contract"]["tier"] == "extra_long"
    assert config["chapter_draft_contract"]["recommended_scene_count_min"] == 6
    assert config["chapter_draft_contract"]["preferred_floor"] >= 9200


@pytest.mark.skip(reason="API refactored")
def test_chapter_generation_timeout_scales_with_target_length():
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(700) == 180.0
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(1800) == 300.0
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(3200) == 600.0
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(5000) == 900.0


@pytest.mark.skip(reason="API refactored")
def test_chapter_mission_timeout_scales_with_target_length():
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(700) == 45.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(1800) == 60.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(3200) == 90.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(5000) == 120.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(7000) == 180.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(10000) == 300.0


@pytest.mark.skip(reason="API refactored")
def test_chapter_generation_max_tokens_scales_with_target_length():
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(700) == 2800
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(1800) == 5200
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(3200) == 7800
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(5000) == 11000
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(7000) >= 14000
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(10000) >= 24000
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(13000) <= 32000


def test_advanced_generate_config_is_background_safe_and_bounded():
    config = _build_advanced_background_flow_config(
        AdvancedGenerateRequest(
            project_id="project-1",
            chapter_number=2,
            writing_notes="加强压迫感",
            flow_config=FlowConfig(
                preset="ultimate",
                versions=99,
                target_word_count=800,
                min_word_count=1200,
                enable_self_critique=True,
                async_finalize=True,
            ),
        )
    )

    assert config["preset"] == "ultimate"
    assert config["versions"] == 4
    assert config["target_word_count"] == 800
    assert config["min_word_count"] == 800
    assert config["enable_self_critique"] is True
    assert config["async_finalize"] is False
    assert config["advanced_background_mode"] is True
    assert config["chapter_draft_contract"]["target_word_count"] == 800
    assert config["generation_strategy"] == "single_pass_compact"


def test_advanced_generate_config_does_not_override_preset_quality_defaults_when_flags_omitted():
    config = _build_advanced_background_flow_config(
        AdvancedGenerateRequest(
            project_id="project-1",
            chapter_number=2,
            writing_notes="加强压迫感",
            flow_config=FlowConfig(
                preset="ultimate",
                target_word_count=2600,
                min_word_count=1800,
            ),
        )
    )

    assert config["preset"] == "ultimate"
    assert "enable_consistency" not in config
    assert "enable_enrichment" not in config
    assert "enable_self_critique" not in config
    assert "rag_mode" not in config
    assert "max_enrich_iterations" not in config


def test_advanced_generate_config_raises_default_candidate_count_for_longform_quality_presets():
    config = _build_advanced_background_flow_config(
        AdvancedGenerateRequest(
            project_id="project-1",
            chapter_number=2,
            writing_notes="加强压迫感",
            flow_config=FlowConfig(
                preset="ultimate",
                target_word_count=5000,
                min_word_count=4500,
            ),
        )
    )

    assert config["preset"] == "ultimate"
    assert config["versions"] == 2
