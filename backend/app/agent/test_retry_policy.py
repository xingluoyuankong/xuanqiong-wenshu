from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.dead_letter import project_dead_letter
from app.agent.retry_policy import classify_error


def test_retry_policy_classifies_transient_and_exhausted_errors():
    decision = classify_error('ProviderTimeout', attempt_count=1, max_attempts=3)
    assert decision.retryable is True
    assert decision.reason == 'transient_error'
    assert decision.delay_seconds == 1
    exhausted = classify_error('ProviderTimeout', attempt_count=3, max_attempts=3)
    assert exhausted.retryable is True
    assert exhausted.reason == 'retry_budget_exhausted'
    assert exhausted.delay_seconds == 0


def test_retry_policy_rejects_unknown_and_policy_errors():
    assert classify_error('UnknownJobKind', attempt_count=1, max_attempts=3).retryable is False
    assert classify_error('UnexpectedError', attempt_count=1, max_attempts=3).reason == 'unclassified_error_requires_review'


def test_dead_letter_projection_is_safe_and_requires_terminal_status():
    job = SimpleNamespace(id='job', run_id='run', user_id=1, project_id='project', kind='provider', status='dead_letter', attempt_count=3, max_attempts=3, error_type='ProviderTimeout', error_detail='safe detail', created_at=None, finished_at=None)
    projected = project_dead_letter(job)
    assert projected['job_id'] == 'job'
    assert 'payload_json' not in projected
    with pytest.raises(ValueError):
        project_dead_letter(SimpleNamespace(status='failed'))
