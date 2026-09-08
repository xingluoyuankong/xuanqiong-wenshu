"""Pure F02 dependency classification; no Runtime/worker/DB fixtures required."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from itertools import permutations, product
from types import MappingProxyType
from collections.abc import Mapping

import pytest

from app.agent.dependency_state import DependencyState, classify_dependencies


def test_no_dependencies_are_ready():
    assert classify_dependencies([], {99: "failed"}) == DependencyState("ready", (), ())


def test_only_completed_dependencies_are_satisfied():
    assert classify_dependencies([3, 1, 3], {1: "completed", 3: "completed"}) == DependencyState("ready", (), ())


@pytest.mark.parametrize("status", ["awaiting_approval", "pending", "running", "retrying", "missing"])
def test_waiting_statuses_do_not_fail_or_satisfy_dependency(status):
    assert classify_dependencies([7], {7: status}) == DependencyState("waiting", (7,), ())


def test_missing_entry_waits_without_changing_mapping():
    from collections import defaultdict
    statuses = defaultdict(lambda: "completed")
    assert classify_dependencies([7], statuses) == DependencyState("waiting", (7,), ())
    assert dict(statuses) == {}


@pytest.mark.parametrize("status", ["failed", "execution_failed", "dead_letter"])
def test_failure_statuses_are_terminal(status):
    assert classify_dependencies([7], {7: status}) == DependencyState("failed", (7,), (7,))


@pytest.mark.parametrize("status", ["cancelled", "rejected"])
def test_cancellation_statuses_are_terminal(status):
    assert classify_dependencies([7], {7: status}) == DependencyState("cancelled", (7,), (7,))


@pytest.mark.parametrize("status", ["approved", "executing", "executed", "succeeded", "queued", "paused", "", "COMPLETED", " completed ", "future_state", None, True, 1, [], {}])
def test_unknown_or_malformed_status_fails_closed(status):
    assert classify_dependencies([7], {7: status}) == DependencyState("failed", (7,), (7,))


def test_unknown_status_value_is_not_retained_in_result():
    result = classify_dependencies([7], {7: "PRIVATE_STATUS_SENTINEL"})
    assert result == DependencyState("failed", (7,), (7,))
    assert "PRIVATE_STATUS_SENTINEL" not in repr(result)


@pytest.mark.parametrize("orders", list(permutations([1, 2, 3])))
def test_failure_precedes_cancellation_and_waiting_in_any_order(orders):
    statuses = {1: "pending", 2: "rejected", 3: "failed"}
    result = classify_dependencies(list(orders), statuses)
    assert result.state == "failed"
    assert result.unresolved == orders
    assert result.terminal == tuple(order for order in orders if order != 1)


@pytest.mark.parametrize("orders", [[1, 2], [2, 1]])
def test_cancellation_precedes_waiting(orders):
    result = classify_dependencies(orders, {1: "pending", 2: "cancelled"})
    assert result == DependencyState("cancelled", tuple(orders), (2,))


def test_unresolved_includes_terminal_and_uses_first_occurrence_order():
    result = classify_dependencies([9, 4, 2, 9, 8, 4, 7], {
        9: "pending", 4: "completed", 2: "rejected", 8: "unknown", 7: "failed",
    })
    assert result == DependencyState("failed", (9, 2, 8, 7), (2, 8, 7))


def test_unknown_failure_precedes_cancellation():
    assert classify_dependencies([1, 2], {1: "rejected", 2: "future"}) == DependencyState("failed", (1, 2), (1, 2))


def test_unrelated_statuses_are_ignored():
    assert classify_dependencies([1], {1: "completed", 2: "unknown", 3: []}) == DependencyState("ready", (), ())


def test_all_mixed_three_dependency_states():
    states = ("completed", "pending", "awaiting_approval", "running", "retrying", "missing", "failed", "execution_failed", "dead_letter", "cancelled", "rejected", "unknown")
    failures = {"failed", "execution_failed", "dead_letter", "unknown"}
    cancellations = {"cancelled", "rejected"}
    for values in product(states, repeat=3):
        statuses = dict(zip((1, 2, 3), values))
        unresolved = tuple(i for i, value in statuses.items() if value != "completed")
        terminal = tuple(i for i, value in statuses.items() if value in failures | cancellations)
        expected = "failed" if any(v in failures for v in values) else "cancelled" if any(v in cancellations for v in values) else "waiting" if unresolved else "ready"
        assert classify_dependencies([1, 2, 3], statuses) == DependencyState(expected, unresolved, terminal), values


def test_inputs_are_unchanged_and_read_only_mapping_supported():
    orders = [3, 1, 3, 2]
    statuses = {1: "completed", 2: "cancelled", 3: "running"}
    before = deepcopy((orders, statuses))
    assert classify_dependencies(orders, MappingProxyType(statuses)) == DependencyState("cancelled", (3, 2), (2,))
    assert (orders, statuses) == before


def test_result_is_frozen_hashable_and_detached_from_inputs():
    orders = [1, 2]
    statuses = {1: "completed", 2: "pending"}
    result = classify_dependencies(orders, statuses)
    with pytest.raises(FrozenInstanceError):
        result.state = "ready"
    with pytest.raises(FrozenInstanceError):
        result.unresolved = ()
    with pytest.raises(FrozenInstanceError):
        result.terminal = ()
    assert isinstance(result.unresolved, tuple) and isinstance(result.terminal, tuple)
    assert {result} == {DependencyState("waiting", (2,), ())}
    orders.clear()
    statuses[2] = "completed"
    assert result == DependencyState("waiting", (2,), ())


def test_calls_do_not_share_accumulated_state():
    first = classify_dependencies([1], {1: "failed"})
    second = classify_dependencies([2], {2: "completed"})
    assert first == DependencyState("failed", (1,), (1,))
    assert second == DependencyState("ready", (), ())


def test_mapping_contract_does_not_require_iteration_or_copy():
    class RequestedOnly(Mapping):
        def __getitem__(self, key):
            if key == 2:
                return "completed"
            raise KeyError(key)

        def __iter__(self):
            raise AssertionError("must not scan unrelated statuses")

        def __len__(self):
            raise AssertionError("must not scan unrelated statuses")

    assert classify_dependencies([2, 3], RequestedOnly()) == DependencyState("waiting", (3,), ())


@pytest.mark.parametrize("orders", [None, (1,), "1", {1}, [True], [False], ["1"], [1.0], [None], [[]], [{}]])
def test_invalid_dependency_shape_raises_type_error(orders):
    with pytest.raises(TypeError):
        classify_dependencies(orders, {})


@pytest.mark.parametrize("orders", [[0], [-1], [1, -9]])
def test_nonpositive_dependency_order_raises_value_error(orders):
    with pytest.raises(ValueError):
        classify_dependencies(orders, {})


@pytest.mark.parametrize("statuses", [None, [], (), "completed"])
def test_statuses_must_be_mapping(statuses):
    with pytest.raises(TypeError):
        classify_dependencies([1], statuses)


def test_validation_errors_do_not_echo_input():
    with pytest.raises(TypeError) as error:
        classify_dependencies(["PRIVATE_ORDER_SENTINEL"], {})
    assert "PRIVATE_ORDER_SENTINEL" not in str(error.value)
