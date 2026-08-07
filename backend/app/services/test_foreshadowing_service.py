# Test foreshadowing_service utility functions
from app.services.foreshadowing_service import ForeshadowingService

class TestSplitSentences:
    def test_empty(self):
        svc = ForeshadowingService(None)
        assert svc._split_sentences('') == []

    def test_chinese_split(self):
        svc = ForeshadowingService(None)
        result = svc._split_sentences('第一句。第二句！第三句？')
        assert len(result) == 3

class TestNormalizeStatusFilter:
    def test_none_returns_none(self):
        result = ForeshadowingService._normalize_status_filter(None)
        assert result is None
