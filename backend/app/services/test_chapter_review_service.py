# Test chapter_review_service interval logic
from app.services.chapter_review_service import ChapterReviewService

svc = ChapterReviewService(None, None, None)

class TestShouldTriggerReview:
    def test_trigger_at_interval_threshold(self):
        assert svc.should_trigger_review(chapter_number=5, review_interval=5) is True

    def test_no_trigger_below_interval(self):
        assert svc.should_trigger_review(chapter_number=3, review_interval=5) is False

    def test_trigger_above_interval(self):
        assert svc.should_trigger_review(chapter_number=7, review_interval=5) is True

    def test_chapter_one_no_trigger(self):
        assert svc.should_trigger_review(chapter_number=1, review_interval=5) is False

    def test_custom_interval(self):
        assert svc.should_trigger_review(chapter_number=3, review_interval=3) is True
        assert svc.should_trigger_review(chapter_number=2, review_interval=3) is False

    def test_last_review_chapter_reset(self):
        result = svc.should_trigger_review(chapter_number=8, review_interval=5, last_review_chapter=0)
        assert result is True

class TestDefaultInterval:
    def test_default_is_5(self):
        assert ChapterReviewService(None, None, None).DEFAULT_REVIEW_INTERVAL == 5
