from app.services.pipeline_orchestrator import PipelineOrchestrator


def test_default_candidate_hints_use_distinct_narrative_strategies():
    hints = PipelineOrchestrator._resolve_style_hints(None, 3)
    assert len(hints) == 3
    assert "冲突最激烈处" in hints[0]
    assert "错误判断" in hints[1]
    assert "对话博弈" in hints[2]
    assert len(set(hints)) == 3
