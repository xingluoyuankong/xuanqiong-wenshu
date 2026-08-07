# Test ai_review_service dataclass validation
from app.services.ai_review_service import ReviewResult, AIReviewService

class TestReviewResult:
    def test_create_review_result(self):
        r = ReviewResult(
            best_version_index=0,
            scores={'immersion': 7, 'pacing': 6, 'hook': 8, 'character': 5},
            overall_evaluation='Good chapter with strong hook',
            critical_flaws=['Pacing slows in middle'],
            refinement_suggestions='Tighten middle section',
            final_recommendation='ACCEPT',
        )
        assert r.best_version_index == 0
        assert r.scores['immersion'] == 7
        assert r.scores['hook'] == 8
        assert len(r.critical_flaws) == 1
        assert r.final_recommendation == 'ACCEPT'

    def test_review_with_no_flaws(self):
        r = ReviewResult(
            best_version_index=2,
            scores={'immersion': 9, 'pacing': 8, 'hook': 9, 'character': 8},
            overall_evaluation='Excellent chapter',
            critical_flaws=[],
            refinement_suggestions='',
            final_recommendation='ACCEPT',
        )
        assert r.best_version_index == 2
        assert len(r.critical_flaws) == 0
        assert r.scores['immersion'] == 9

    def test_review_with_raw_response(self):
        r = ReviewResult(
            best_version_index=1,
            scores={'immersion': 5, 'pacing': 5, 'hook': 5, 'character': 5},
            overall_evaluation='Middling',
            critical_flaws=['Weak character voice'],
            refinement_suggestions='Add more character depth',
            final_recommendation='REVISE',
            raw_response='Some raw LLM output',
        )
        assert r.raw_response == 'Some raw LLM output'
        assert r.final_recommendation == 'REVISE'
