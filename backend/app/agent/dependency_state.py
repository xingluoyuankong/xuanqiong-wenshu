"""Pure dependency-state classification, not a durable continuation scheduler.

Only a completed *step* satisfies a dependency. Approval and job statuses must
not be interpreted as successful step completion. Inputs are never mutated.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class DependencyState:
    """Ordered, deduplicated dependency facts.

    unresolved contains every non-completed dependency, including terminal ones.
    terminal is its failed/cancelled/unknown subset. Failure takes precedence
    over cancellation, which takes precedence over waiting.
    """

    state: Literal["ready", "waiting", "failed", "cancelled"]
    unresolved: tuple[int, ...]
    terminal: tuple[int, ...]


_WAITING = frozenset({"awaiting_approval", "pending", "running", "retrying", "missing"})
_FAILED = frozenset({"failed", "execution_failed", "dead_letter"})
_CANCELLED = frozenset({"cancelled", "rejected"})


def classify_dependencies(
    dependency_orders: list[int], statuses: Mapping[int, str]
) -> DependencyState:
    """Classify the requested steps without IO, coercion, or state changes.

    Missing entries wait; explicit malformed/unknown values fail closed. A
    duplicate dependency contributes once, in first-occurrence order. Unrelated
    mapping entries are ignored. Invalid input shape/order raises TypeError or
    ValueError with a fixed message rather than fabricating dependency facts.
    This helper does not enqueue work, retry steps, or validate a plan's DAG.
    """
    if not isinstance(dependency_orders, list):
        raise TypeError("dependency_orders must be a list of positive integers")
    if not isinstance(statuses, Mapping):
        raise TypeError("statuses must be a mapping")
    for order in dependency_orders:
        if type(order) is not int:
            raise TypeError("dependency orders must be integers")
        if order <= 0:
            raise ValueError("dependency orders must be positive")

    unresolved: list[int] = []
    terminal: list[int] = []
    has_failure = False
    has_cancellation = False
    for order in dict.fromkeys(dependency_orders):
        status = statuses.get(order, "missing")
        if isinstance(status, str) and status == "completed":
            continue
        unresolved.append(order)
        if isinstance(status, str) and status in _WAITING:
            continue
        terminal.append(order)
        if isinstance(status, str) and status in _CANCELLED:
            has_cancellation = True
        elif isinstance(status, str) and status in _FAILED:
            has_failure = True
        else:
            # Unknown statuses are terminal failures, never success or waiting.
            has_failure = True

    state: Literal["ready", "waiting", "failed", "cancelled"]
    if has_failure:
        state = "failed"
    elif has_cancellation:
        state = "cancelled"
    elif unresolved:
        state = "waiting"
    else:
        state = "ready"
    return DependencyState(state, tuple(unresolved), tuple(terminal))
