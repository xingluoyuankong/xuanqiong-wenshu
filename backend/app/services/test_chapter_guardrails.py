# Test chapter_guardrails dataclass validation
from app.services.chapter_guardrails import Violation, GuardrailResult, ChapterGuardrails

class TestViolation:
    def test_create_violation(self):
        v = Violation(type='forbidden_name', severity='high', description='Broke continuity')
        assert v.type == 'forbidden_name'
        assert v.severity == 'high'
        assert v.position is None

    def test_violation_with_position(self):
        v = Violation(type='omniscient_cue', severity='medium', description='Test', position=42)
        assert v.position == 42

class TestGuardrailResult:
    def test_passed_no_violations(self):
        r = GuardrailResult(passed=True, violations=[])
        assert r.passed is True
        assert len(r.violations) == 0

    def test_failed_with_violations(self):
        v = Violation(type='test', severity='low', description='td')
        r = GuardrailResult(passed=False, violations=[v])
        assert r.passed is False
        assert len(r.violations) == 1
        assert r.violations[0].type == 'test'

    def test_summary_includes_violation_count(self):
        v1 = Violation(type='a', severity='high', description='d1')
        v2 = Violation(type='b', severity='low', description='d2')
        r = GuardrailResult(passed=False, violations=[v1, v2])
        assert r.passed is False
        assert len(r.violations) == 2
