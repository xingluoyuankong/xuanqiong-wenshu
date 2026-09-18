from datetime import datetime

from app.services.pipeline_orchestrator import PipelineOrchestrator


class TestPipelineOrchestratorOverviewReuse:
    def test_resolve_overview_change_level_returns_none_when_hash_matches(self):
        previous = {
            "overview_hash": "same-hash",
            "outline_title": "第一章",
            "previous_summary": "旧摘要",
        }
        current = {
            "overview_hash": "same-hash",
            "outline_title": "第一章-改名也应视为复用命中",
            "previous_summary": "新摘要",
        }

        change_level, changed_fields = PipelineOrchestrator._resolve_overview_change_level(previous, current)

        assert change_level == "none"
        assert changed_fields == []

    def test_build_reuse_decision_marks_none_and_light_as_reusable(self):
        assert PipelineOrchestrator._build_reuse_decision("none", []) == {
            "change_level": "none",
            "changed_fields": [],
            "reused": True,
            "skip_self_critique": True,
        }
        assert PipelineOrchestrator._build_reuse_decision("light", ["previous_summary"])["skip_self_critique"] is True
        assert PipelineOrchestrator._build_reuse_decision("medium", ["previous_summary"])["skip_self_critique"] is False

    def test_build_reused_self_critique_summary_preserves_previous_payload_and_marks_reused(self):
        previous_summary = {
            "status": "completed",
            "final_score": 86,
            "major_count": 1,
            "priority_fixes": [{"dimension": "logic", "suggested_fix": "补足承接"}],
            "optimization_logs": [{"stage": "structural", "issue_count": 1, "changed": True}],
        }
        reuse_decision = PipelineOrchestrator._build_reuse_decision("light", ["previous_summary"])
        overview_bundle = {"overview_hash": "new-hash", "previous_summary": "已更新"}

        payload = PipelineOrchestrator._build_reused_self_critique_summary(
            previous_summary,
            reuse_decision=reuse_decision,
            overview_bundle=overview_bundle,
            source_version_id=12,
        )

        assert payload["status"] == "reused"
        assert payload["iterations"] == 0
        assert payload["reuse_decision"] == reuse_decision
        assert payload["overview_bundle"] == overview_bundle
        assert payload["reused_from_version_id"] == 12
        assert payload["final_score"] == 86
        assert payload["major_count"] == 1
        assert payload["optimization_logs"] == [{"stage": "structural", "issue_count": 1, "changed": True}]
        assert isinstance(datetime.fromisoformat(payload["reused_at"]), datetime)

    def test_preserve_non_regressive_content_keeps_previous_when_candidate_collapses(self):
        previous = "甲" * 6000
        candidate = "乙" * 44

        selected, guard = PipelineOrchestrator._preserve_non_regressive_content(
            previous_content=previous,
            candidate_content=candidate,
            stage_label="reader_polish",
            min_word_count=5500,
        )

        assert selected == previous
        assert guard is not None
        assert guard["stage"] == "reader_polish"
        assert guard["reason"] == "catastrophic_shrinkage"
        assert guard["previous_word_count"] == 6000
        assert guard["candidate_word_count"] == 44
        assert guard["min_word_count"] == 5500

    def test_preserve_non_regressive_content_accepts_shorter_candidate_when_still_meets_minimum(self):
        previous = "甲" * 6000
        candidate = "乙" * 5600

        selected, guard = PipelineOrchestrator._preserve_non_regressive_content(
            previous_content=previous,
            candidate_content=candidate,
            stage_label="self_critique",
            min_word_count=5500,
        )

        assert selected == candidate
        assert guard is None

    def test_preserve_non_regressive_content_rejects_empty_candidate(self):
        previous = "甲" * 3200

        selected, guard = PipelineOrchestrator._preserve_non_regressive_content(
            previous_content=previous,
            candidate_content="   ",
            stage_label="consistency_repair",
            min_word_count=2400,
        )

        assert selected == previous
        assert guard is not None
        assert guard["reason"] == "empty_candidate"
        assert guard["candidate_word_count"] == 0
