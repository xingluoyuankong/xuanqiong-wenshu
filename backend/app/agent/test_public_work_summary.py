from app.agent.schemas import AgentPublicWorkSummary


def test_public_work_summary_schema_normalizes_controls_and_redacts_private_markers() -> None:
    summary = AgentPublicWorkSummary(
        action_id="schema:redaction",
        phase="planning",
        current_action="\x00正在建立计划。 system_prompt: hidden instruction",
        completed_action="token=PRIVATE_TOKEN_123456",
        input_scope=[],
        revision=0,
    )

    assert summary.current_action == "正在建立计划。 [已脱敏]"
    assert summary.completed_action == "[已脱敏]"
    assert "hidden instruction" not in summary.current_action
    assert "PRIVATE_TOKEN_123456" not in str(summary.model_dump())
