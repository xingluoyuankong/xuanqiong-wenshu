from __future__ import annotations

from .provider_attempt import ProviderAttemptLedger, classify_provider_error


class HTTP429Error(Exception):
    status_code = 429


class TimeoutFixture(Exception):
    pass


class CancelledFixture(Exception):
    pass


def test_ledger_records_success_and_redacted_digest() -> None:
    ledger = ProviderAttemptLedger(run_id="run-1")
    first = ledger.begin(role="candidate_writer", provider_ref="openai-compatible", model_ref="model-a")
    ledger.mark_first_token(first.attempt_id)
    ledger.finish(first.attempt_id, output="候选正文")

    snapshot = ledger.snapshot()
    assert snapshot["selected_provider_attempt"] == 1
    assert snapshot["fallback_used"] is False
    assert snapshot["provider_attempts"][0]["status"] == "succeeded"
    assert snapshot["provider_attempts"][0]["output_digest"]
    assert "候选正文" not in str(snapshot)


def test_ledger_is_idempotent_and_supports_fallback_chain() -> None:
    ledger = ProviderAttemptLedger(run_id="run-2")
    primary = ledger.begin(role="response", provider_ref="provider-a", model_ref="model-a", attempt_id="attempt-a")
    same = ledger.begin(role="response", provider_ref="provider-a", model_ref="model-a", attempt_id="attempt-a")
    assert same is primary
    ledger.fail(primary.attempt_id, HTTP429Error())
    fallback = ledger.begin(role="response", provider_ref="provider-b", model_ref="model-b", fallback_from_attempt=1, attempt_id="attempt-b")
    ledger.finish(fallback.attempt_id, output="ok")

    snapshot = ledger.snapshot()
    assert len(snapshot["provider_attempts"]) == 2
    assert snapshot["provider_attempts"][0]["error_category"] == "RATE_LIMIT"
    assert snapshot["provider_attempts"][1]["fallback_from_attempt"] == 1
    assert snapshot["selected_provider_attempt"] == 2
    assert snapshot["fallback_used"] is True


def test_error_categories_cover_timeout_cancel_and_network() -> None:
    assert classify_provider_error(TimeoutFixture()) == "TIMEOUT"
    assert classify_provider_error(CancelledFixture()) == "CANCELLED"
    assert classify_provider_error(HTTP429Error()) == "RATE_LIMIT"


def test_rehydrate_closes_interrupted_running_attempt() -> None:
    ledger = ProviderAttemptLedger.from_snapshot(
        run_id="run-recovery",
        snapshot={
            "provider_attempts": [
                {
                    "attempt": 1,
                    "role": "response",
                    "provider_ref": "provider-a",
                    "model_ref": "model-a",
                    "status": "running",
                    "started_at": "2026-09-01T10:00:00+00:00",
                }
            ]
        },
    )

    record = ledger.snapshot()["provider_attempts"][0]
    assert record["status"] == "failed"
    assert record["error_category"] == "NETWORK_DISCONNECT"
    assert record["finished_at"]
    assert record["cancel_observed"] is False
