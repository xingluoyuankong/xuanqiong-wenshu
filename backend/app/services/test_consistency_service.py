"""consistency_service core tests (dataclass + enum only)"""
import pytest
from app.services.consistency_service import (
    ConsistencyCheckResult, ConsistencyViolation, ViolationSeverity
)



def test_violation_severity_values():
    assert ViolationSeverity.CRITICAL == "critical"
    assert ViolationSeverity.MAJOR == "major"
    assert ViolationSeverity.MINOR == "minor"

def test_consistency_check_result_fields():
    r = ConsistencyCheckResult(
        is_consistent=True,
        violations=[],
        summary="No issues found",
        check_time_ms=120,
        status="passed",
    )
    assert r.is_consistent == True
    assert r.summary == "No issues found"
    assert r.status == "passed"
    assert r.check_time_ms == 120

def test_consistency_violation_fields():
    v = ConsistencyViolation(
        severity=ViolationSeverity.MAJOR,
        category="plot",
        description="Missing hook at chapter end",
        location="chapter 5 ending",
        suggested_fix="Add cliffhanger",
        confidence=0.85,
    )
    assert v.severity == ViolationSeverity.MAJOR
    assert v.category == "plot"
    assert v.description == "Missing hook at chapter end"
    assert v.confidence == 0.85