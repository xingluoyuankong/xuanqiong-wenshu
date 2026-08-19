from types import SimpleNamespace

from app.api.routers.updates import (
    _is_log_stream_event,
    _resolve_stream_cursor,
    _sse_frame,
    _stream_sse_envelope,
)


def test_update_stream_cursor_prefers_latest_reconnect_position():
    assert _resolve_stream_cursor(3, 7) == 7
    assert _resolve_stream_cursor(9, 4) == 9
    assert _resolve_stream_cursor(0, None) == 0


def test_log_stream_excludes_content_delta_but_keeps_runtime_channels():
    assert not _is_log_stream_event("content_delta")
    assert _is_log_stream_event("log")
    assert _is_log_stream_event("progress")
    assert _is_log_stream_event("diagnostic")
    assert _is_log_stream_event("task_completed")
    assert _is_log_stream_event("task_cancelled")


def test_sse_frame_has_explicit_event_name_and_stable_id():
    frame = _sse_frame("log", {"message": "hi"}, event_id=42)
    assert "id: 42" in frame
    assert "event: log" in frame
    assert frame.endswith("\n\n")


def test_stream_sse_envelope_projects_channel_and_sequence_for_legacy_events():
    event = SimpleNamespace(
        task_id="t-1",
        event_id=17,
        event_type="log",
        status="running",
        stage="drafting",
        progress=33.0,
        message="写正文",
        created_at=None,
        payload=None,
    )
    envelope = _stream_sse_envelope(event)
    assert envelope["channel"] == "log"
    assert envelope["event_sequence"] == 17
    assert envelope["event_id"] == 17
    assert envelope["event_type"] == "log"


def test_stream_sse_envelope_prefers_persisted_channel_payload():
    event = SimpleNamespace(
        task_id="t-2",
        event_id=18,
        event_type="content_delta",
        status=None,
        stage=None,
        progress=None,
        message=None,
        created_at=None,
        payload={"channel": "content", "event_sequence": 18, "text": "正文"},
    )
    envelope = _stream_sse_envelope(event)
    assert envelope["channel"] == "content"
    assert envelope["payload"]["text"] == "正文"
