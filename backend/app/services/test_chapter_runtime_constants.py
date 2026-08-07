# Test chapter_runtime_constants
from app.services.chapter_runtime_constants import CHAPTER_STALE_TIMEOUT
from datetime import timedelta

class TestChapterRuntimeConstants:
    def test_stale_timeout_is_10_minutes(self):
        assert CHAPTER_STALE_TIMEOUT == timedelta(minutes=10)

    def test_stale_timeout_in_seconds(self):
        assert CHAPTER_STALE_TIMEOUT.total_seconds() == 600
