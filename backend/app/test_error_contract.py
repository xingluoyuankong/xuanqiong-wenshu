from app.main import _format_root_cause


def test_root_cause_formatter_unwraps_single_task_group_child() -> None:
    leaf = RuntimeError("sqlite write collision")
    wrapped = ExceptionGroup("unhandled errors in a TaskGroup", [leaf])

    assert _format_root_cause(wrapped) == "RuntimeError: sqlite write collision"


def test_root_cause_formatter_follows_cause_after_task_group_unwrap() -> None:
    leaf = ValueError("real write failure")
    middle = RuntimeError("outer request failure")
    middle.__cause__ = leaf
    wrapped = ExceptionGroup("unhandled errors in a TaskGroup", [middle])

    assert _format_root_cause(wrapped) == "ValueError: real write failure"
