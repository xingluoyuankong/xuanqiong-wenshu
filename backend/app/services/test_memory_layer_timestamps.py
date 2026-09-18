from datetime import datetime

from app.models.memory_layer import _utcnow_naive


def test_memory_layer_utc_clock_preserves_legacy_naive_utc_storage_shape():
    value = _utcnow_naive()

    assert isinstance(value, datetime)
    assert value.tzinfo is None