from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.work_trace_contract import WorkTraceDelta


def test_work_trace_contract_accepts_bounded_public_delta():
    delta = WorkTraceDelta(
        trace_id="trace-1", run_id="run-1", phase="act", kind="tool",
        action_id="action-1", message="正在读取章节索引", progress=32,
        capability_id="content.search",
    )
    assert delta.progress == 32
    assert delta.message == "正在读取章节索引"


def test_work_trace_contract_rejects_private_or_oversized_payload():
    with pytest.raises(ValidationError):
        WorkTraceDelta(trace_id="t", run_id="r", message="private_reasoning: hidden")
    with pytest.raises(ValidationError):
        WorkTraceDelta(trace_id="t", run_id="r", message="x" * 1001)
