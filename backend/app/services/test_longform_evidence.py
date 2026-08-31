"""Regression tests for redacted T-25 long-form failure evidence."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.longform_evidence import (
    build_longform_failure_evidence,
    validate_longform_failure_evidence,
)


def _sample_report():
    return build_longform_failure_evidence(
        source_db=r"D:\secrets\real-asgi-longform.db",
        task={
            "task_id": "task-1",
            "status": "failed",
            "stage": "segment_2",
            "progress": 40,
            "attempt": 2,
            "retry_count": 1,
            "elapsed_ms": 1234,
            "error_code": "LONGFORM_RUNTIME_INVALID",
        },
        runtime={
            "segment_count": 3,
            "plan": {
                "plan_key": "private-plan-key",
                "target_word_count": 9000,
                "min_word_count": 7000,
                "segment_word_limit": 3000,
                "segments": [{}, {}, {}],
                "book_context": {"title": "private title"},
            },
            "checkpoint": {
                "next_segment_index": 1,
                "used_words": 3000,
                "total_tokens": 2000,
                "assembled_text": "PRIVATE PROSE MUST NOT APPEAR",
                "completed_segments": [{
                    "index": 0,
                    "word_count": 3000,
                    "char_count": 5000,
                    "target_words": 3000,
                    "token_usage": 2000,
                    "fingerprint": "0123456789abcdef0123456789abcdef01234567",
                    "content": "PRIVATE SEGMENT",
                }],
            },
        },
        events=[
            {"event_type": "content_delta", "message": "PRIVATE EVENT MESSAGE", "payload": {"content_delta": "PRIVATE DELTA"}},
            {"event_type": "task_failed", "message": "PRIVATE PROVIDER RESPONSE", "payload": {"response": "PRIVATE RESPONSE"}},
        ],
        content="PRIVATE FULL CHAPTER",
        failure={
            "error_code": "LONGFORM_RUNTIME_INVALID",
            "error_class": "LongformGenerationContractError",
            "retryable": False,
            "normalized_reason": "checkpoint_contract_invalid",
            "error_detail": "PRIVATE RAW ERROR",
        },
    )


def test_failure_projection_excludes_prose_and_provider_payloads():
    report = _sample_report()
    encoded = json.dumps(report, ensure_ascii=False)

    assert report["source_db"] == "real-asgi-longform.db"
    assert report["redaction"]["content_emitted"] is False
    assert report["checkpoint"]["assembled_text_chars"] > 0
    assert report["checkpoint"]["segments"][0]["fingerprint"] == "0123456789abcdef0123456789abcdef01234567"
    assert report["events"]["content_delta_count"] == 1
    assert "error_detail" not in report["failure"]
    for secret in ("PRIVATE FULL CHAPTER", "PRIVATE PROSE MUST NOT APPEAR", "PRIVATE DELTA", "PRIVATE RESPONSE", "PRIVATE RAW ERROR"):
        assert secret not in encoded
    assert "\"assembled_text\":" not in encoded
    assert "\"payload\":" not in encoded
    assert validate_longform_failure_evidence(report) == []


def test_failure_projection_hashes_a_corrupted_fingerprint_instead_of_emitting_it():
    secret = "PRIVATE FINGERPRINT CONTENT"
    report = build_longform_failure_evidence(
        source_db="real.db",
        task={"status": "failed"},
        runtime={"checkpoint": {"completed_segments": [{"fingerprint": secret}]}},
        failure={"error_code": "FAILED"},
    )

    fingerprint = report["checkpoint"]["segments"][0]["fingerprint"]
    assert fingerprint != secret
    assert fingerprint is not None and len(fingerprint) == 64
    assert secret not in json.dumps(report, ensure_ascii=False)


def test_failure_projection_without_version_content_uses_checkpoint_hash_only():
    report = build_longform_failure_evidence(
        source_db="real.db",
        task={"status": "failed"},
        runtime={"checkpoint": {"assembled_text": "CHECKPOINT CONTENT"}},
        failure={"error_code": "FAILED"},
    )

    assert report["redaction"]["content_sha256"] == report["checkpoint"]["assembled_text_sha256"]
    assert report["redaction"]["content_chars"] == len("CHECKPOINT CONTENT")


def test_failure_smoke_does_not_hash_a_stale_chapter_version():
    smoke = Path(__file__).resolve().parents[2] / "scripts" / "real_asgi_longform_generation_smoke.py"
    source = smoke.read_text(encoding="utf-8")

    assert "content=version.content" not in source
    assert "source_db=DB_PATH" in source


def test_failure_projection_embeds_the_same_checkpoint_validation_as_cli():
    report = build_longform_failure_evidence(
        source_db="real.db",
        task={"status": "failed"},
        runtime={
            "plan": {"segments": [{}, {}]},
            "checkpoint": {
                "next_segment_index": 3,
                "completed_segments": [{"index": 0}, {"index": 1}],
            },
        },
        failure={"error_code": "FAILED"},
    )

    assert report["validation"]["valid"] is False
    assert "next_segment_index exceeds segment_count" in report["validation"]["errors"]
    assert report["validation"]["errors"] == validate_longform_failure_evidence(report)


def test_failure_projection_detects_tampered_report_shape():
    report = _sample_report()
    report["checkpoint"]["segments"].append({"index": 9})
    report["events"]["event_count"] = 1

    errors = validate_longform_failure_evidence(report)

    assert "completed_segment_count does not match segments" in errors
    assert "event_type_counts does not match event_count" in errors


def test_failure_projection_cannot_be_marked_as_unredacted():
    report = _sample_report()
    report["redaction"]["provider_response_emitted"] = True

    assert "redaction.provider_response_emitted must be false" in validate_longform_failure_evidence(report)
