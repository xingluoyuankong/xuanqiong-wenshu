from __future__ import annotations

import pytest

from app.agent.state_machine import (
    RUN_STATUSES,
    RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    InvalidRunStatus,
    InvalidRunTransition,
    can_transition,
    is_recovery_ready,
    is_terminal_run_status,
    normalize_run_status,
    validate_transition,
)


def test_runtime_status_contract_is_explicit() -> None:
    assert RUN_STATUSES == {
        "created",
        "planning",
        "running",
        "awaiting_approval",
        "paused",
        "cancelling",
        "cancelled",
        "failed",
        "completed",
    }
    assert TERMINAL_RUN_STATUSES == {"cancelled", "failed", "completed"}
    assert set(RUN_TRANSITIONS) == RUN_STATUSES


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" CREATED ", "created"), ("Awaiting_Approval", "awaiting_approval")],
)
def test_normalize_run_status(raw: str, expected: str) -> None:
    assert normalize_run_status(raw) == expected


@pytest.mark.parametrize("value", [None, "", "unknown", "recovery_ready", 42])
def test_invalid_status_is_rejected(value: object) -> None:
    with pytest.raises(InvalidRunStatus):
        normalize_run_status(value)


@pytest.mark.parametrize("status", sorted(RUN_STATUSES))
def test_same_status_update_is_always_allowed(status: str) -> None:
    assert can_transition(status, status)
    assert validate_transition(status, status) == (status, status)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("created", "planning"),
        ("created", "running"),
        ("created", "cancelling"),
        ("planning", "running"),
        ("planning", "awaiting_approval"),
        ("running", "planning"),
        ("running", "completed"),
        ("awaiting_approval", "running"),
        ("paused", "running"),
        ("paused", "completed"),
        ("cancelling", "cancelled"),
    ],
)
def test_runtime_transitions_are_allowed(source: str, target: str) -> None:
    assert can_transition(source, target)
    assert validate_transition(source, target) == (source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("running", "created"),
        ("awaiting_approval", "planning"),
        ("cancelling", "running"),
        ("cancelling", "paused"),
        ("paused", "created"),
        ("completed", "running"),
        ("failed", "planning"),
        ("cancelled", "created"),
    ],
)
def test_invalid_runtime_transitions_are_rejected(source: str, target: str) -> None:
    assert not can_transition(source, target)
    with pytest.raises(InvalidRunTransition):
        validate_transition(source, target)


@pytest.mark.parametrize("status", sorted(TERMINAL_RUN_STATUSES))
def test_terminal_statuses_are_locked(status: str) -> None:
    assert is_terminal_run_status(status)
    for target in sorted(RUN_STATUSES):
        assert can_transition(status, target) is (target == status)


def test_recovery_ready_is_a_paused_phase_marker() -> None:
    assert is_recovery_ready(status="paused", phase="recovery_ready")
    assert is_recovery_ready(status="PAUSED", phase="RECOVERY_READY")
    assert not is_recovery_ready(status="running", phase="recovery_ready")
    assert not is_recovery_ready(status="paused", phase="user")
    assert not can_transition("paused", "recovery_ready")