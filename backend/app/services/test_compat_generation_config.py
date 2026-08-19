from app.api.routers.writer import (
    _build_advanced_background_flow_config,
    _build_compat_generate_flow_config,
    _calculate_generation_timeout_seconds,
)
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
    # ultimate 预设必须真正开启质量功能（历史缺陷：这些键被省略，
    # 导致 PipelineConfig 的全 False 默认值生效，功能从未实际运行）
    assert config["enable_enrichment"] is True
    assert config["enable_consistency"] is True
    assert config["enable_self_critique"] is True
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


def test_chapter_generation_timeout_scales_with_target_length():
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(700) == 120.0
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(1800) == 200.0
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(3200) == 600.0
    assert PipelineOrchestrator._resolve_chapter_generation_timeout(5000) == 900.0


def test_chapter_mission_timeout_scales_with_target_length():
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(700) == 20.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(1800) == 30.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(3200) == 90.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(5000) == 120.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(7000) == 180.0
    assert PipelineOrchestrator._resolve_chapter_mission_timeout(10000) == 300.0


@pytest.mark.anyio
async def test_short_quality_config_disables_expensive_writing_ledgers_by_default():
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._resolve_version_count = lambda _value: _async_one()
    config = await orchestrator._resolve_config({
        "preset": "enhanced",
        "target_word_count": 1200,
        "min_word_count": 900,
    })

    assert config.target_word_count == 1200
    assert config.enable_constitution is False
    assert config.enable_persona is False
    assert config.enable_foreshadowing is False
    assert config.enable_faction is False
    assert config.enable_six_dimension is False
    assert config.enable_consistency is False
    assert config.enable_enrichment is False
    assert config.enable_self_critique is False
    assert config.enable_reader_sim is False


@pytest.mark.anyio
async def test_short_quality_config_keeps_explicit_writing_ledgers_enabled():
    orchestrator = PipelineOrchestrator.__new__(PipelineOrchestrator)
    orchestrator._resolve_version_count = lambda _value: _async_one()
    config = await orchestrator._resolve_config({
        "preset": "enhanced",
        "target_word_count": 1200,
        "enable_foreshadowing": True,
    })

    assert config.enable_foreshadowing is True


async def _async_one():
    return 1


def test_chapter_generation_max_tokens_scales_with_target_length():
    # 短章受独立的响应延迟预算约束，避免网关为超额输出长期占槽；
    # 从 2500 字起恢复原有中长篇输出比例。
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(700) == 2200
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(1200) == 2640
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(1800) == 3600
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(3200) == 9600
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(5000) == 18000
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(7000) >= 26000
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(10000) >= 40000
    assert PipelineOrchestrator._resolve_chapter_generation_max_tokens(13000) <= 56000


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



def test_generation_config_preserves_segment_limit_and_clamps_timeout():
    with pytest.raises(ValueError):
        GenerateChapterRequest(chapter_number=1, segment_word_limit=14000)
    with pytest.raises(ValueError):
        FlowConfig(generation_timeout_seconds=14401)

    compat = _build_compat_generate_flow_config(
        GenerateChapterRequest(
            chapter_number=1,
            target_word_count=20000,
            min_word_count=18000,
            segment_word_limit=12000,
            generation_timeout_seconds=60,
        )
    )
    assert compat["segment_word_limit"] == 12000
    assert compat["generation_timeout_seconds"] == 60
    assert _calculate_generation_timeout_seconds(compat) == 15 * 60

    advanced = _build_advanced_background_flow_config(
        AdvancedGenerateRequest(
            project_id="project-1",
            chapter_number=1,
            flow_config=FlowConfig(
                target_word_count=20000,
                min_word_count=18000,
                segment_word_limit=500,
                generation_timeout_seconds=14400,
            ),
        )
    )
    assert advanced["segment_word_limit"] == 500
    assert advanced["generation_timeout_seconds"] == 14400
    assert _calculate_generation_timeout_seconds(advanced) == 14400


def test_generation_config_defaults_are_safe_for_longform_and_auto_timeout():
    config = _build_compat_generate_flow_config(
        GenerateChapterRequest(chapter_number=1, target_word_count=20000)
    )
    assert config["segment_word_limit"] == 4500
    assert config["generation_timeout_seconds"] == 0
    timeout = _calculate_generation_timeout_seconds(config)
    assert 15 * 60 <= timeout <= 4 * 60 * 60
