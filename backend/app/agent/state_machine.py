"""集中管理 AgentRun 生命周期转移规则。

本模块保持纯函数：不访问数据库、不生成事件、不执行副作用。运行时服务
负责把 InvalidRunTransition 映射为业务冲突，并负责事务、版本号和审计。
"""
from __future__ import annotations

from collections.abc import Mapping

RUN_STATUSES = frozenset({
    "created",
    "planning",
    "running",
    "awaiting_approval",
    "paused",
    "cancelling",
    "cancelled",
    "failed",
    "completed",
})
TERMINAL_RUN_STATUSES = frozenset({"cancelled", "failed", "completed"})
CLAIMABLE_RUN_STATUSES = frozenset({"created", "planning", "running"})
RECOVERY_READY_PHASE = "recovery_ready"

# created -> terminal is retained for existing bootstrap/import call sites that
# create a Run and immediately mark a fixture result. Production paths still
# travel through planning/running or cancelling and are tightened by commands.
RUN_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "created": frozenset(RUN_STATUSES),
    "planning": frozenset({"planning", "running", "awaiting_approval", "paused", "cancelling", "failed", "completed"}),
    "running": frozenset({"planning", "running", "awaiting_approval", "paused", "cancelling", "failed", "completed"}),
    "awaiting_approval": frozenset({"awaiting_approval", "running", "paused", "cancelling", "failed"}),
    "paused": frozenset({"paused", "planning", "running", "awaiting_approval", "cancelling", "cancelled", "failed", "completed"}),
    "cancelling": frozenset({"cancelling", "cancelled", "failed"}),
    "cancelled": frozenset({"cancelled"}),
    "failed": frozenset({"failed"}),
    "completed": frozenset({"completed"}),
}


class InvalidRunStatus(ValueError):
    """Raised when a lifecycle status is outside the AgentRun contract."""


class InvalidRunTransition(ValueError):
    """Raised when a Run attempts a transition outside the lifecycle graph."""


def normalize_run_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status not in RUN_STATUSES:
        raise InvalidRunStatus(f"invalid run status: {status or '<empty>'}")
    return status


def is_terminal_run_status(value: object) -> bool:
    try:
        return normalize_run_status(value) in TERMINAL_RUN_STATUSES
    except InvalidRunStatus:
        return False


def is_recovery_ready(*, status: object, phase: object) -> bool:
    """Recovery-ready is a phase marker carried by a paused Run, not a status."""
    try:
        normalized_status = normalize_run_status(status)
    except InvalidRunStatus:
        return False
    return normalized_status == "paused" and str(phase or "").strip().lower() == RECOVERY_READY_PHASE


def is_claimable_run(*, status: object, phase: object = "") -> bool:
    """Return whether a Run may be claimed by an execution worker."""
    try:
        normalized_status = normalize_run_status(status)
    except InvalidRunStatus:
        return False
    return normalized_status in CLAIMABLE_RUN_STATUSES or is_recovery_ready(status=normalized_status, phase=phase)


def can_transition(current: object, target: object) -> bool:
    try:
        current_status = normalize_run_status(current)
        target_status = normalize_run_status(target)
    except InvalidRunStatus:
        return False
    return target_status in RUN_TRANSITIONS[current_status]


def validate_transition(current: object, target: object) -> tuple[str, str]:
    current_status = normalize_run_status(current)
    target_status = normalize_run_status(target)
    if target_status not in RUN_TRANSITIONS[current_status]:
        raise InvalidRunTransition(f"invalid AgentRun transition: {current_status} -> {target_status}")
    return current_status, target_status