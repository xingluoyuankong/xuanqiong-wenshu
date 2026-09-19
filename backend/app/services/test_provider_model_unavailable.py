from fastapi import HTTPException

from app.services.generation_call_service import classify_provider_error, is_retryable_http_exception


def test_model_not_found_503_is_not_retryable():
    exc = HTTPException(
        status_code=503,
        detail={
            "code": "PROVIDER_MODEL_UNAVAILABLE",
            "message": "No available channel for model __test__",
            "retryable": False,
        },
    )
    assert classify_provider_error(exc) == "model_unavailable"
    assert is_retryable_http_exception(exc) is False


def test_raw_no_available_channel_text_is_classified():
    exc = HTTPException(status_code=503, detail="model_not_found: no available channel")
    assert classify_provider_error(exc) == "model_unavailable"
    assert is_retryable_http_exception(exc) is False
