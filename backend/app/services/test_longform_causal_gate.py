from app.services.longform_context_service import (
    CastPlan,
    ForeshadowingChapterTask,
    LongformContextPackage,
    LongformContextService,
)


def _package_with_pending_causal_chain() -> LongformContextPackage:
    return LongformContextPackage(
        project_id="p-causal-gate",
        chapter_number=5,
        prompt_text="",
        cast_plan=CastPlan(
            target_character_count=8,
            planned_character_count=2,
            chapter_focus_names=["Lin Qi"],
        ),
        foreshadowing_task=ForeshadowingChapterTask(),
        timeline_digest={
            "causal_chains": [
                {
                    "cause_chapter": 4,
                    "cause": "Lin Qi steals the ledger code",
                    "effect": "The archive can trace the missing code and pressure Shen Fang",
                    "status": "pending",
                    "importance": 9,
                    "characters": ["Lin Qi", "Shen Fang"],
                }
            ]
        },
    )


def test_continuity_gate_warns_when_pending_causal_chain_is_not_carried():
    gate = LongformContextService.evaluate_continuity_quality(
        content="Lin Qi walks through the market and talks about the weather.",
        package=_package_with_pending_causal_chain(),
        chapter_mission={},
    )

    assert gate.passed is True
    assert gate.metrics["pending_causal_gap_count"] == 1
    assert any(item["code"] == "pending_causal_chain_not_carried" for item in gate.warnings)
    assert any(item["code"] == "carry_causal_chain_patch" for item in gate.patch_suggestions)


def test_continuity_gate_accepts_visible_causal_chain_carry_forward():
    gate = LongformContextService.evaluate_continuity_quality(
        content="Lin Qi finds the archive already tracing the ledger code, and Shen Fang must choose whether to cover for him.",
        package=_package_with_pending_causal_chain(),
        chapter_mission={},
    )

    assert gate.metrics["pending_causal_gap_count"] == 0
    assert not any(item["code"] == "pending_causal_chain_not_carried" for item in gate.warnings)
