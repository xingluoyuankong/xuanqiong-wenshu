# Test emotion_service static methods
from app.services.emotion_service import EmotionService
import hashlib

class TestGetChapterHash:
    def test_deterministic(self):
        h1 = EmotionService.get_chapter_hash('hello')
        h2 = EmotionService.get_chapter_hash('hello')
        assert h1 == h2

    def test_different_input(self):
        h1 = EmotionService.get_chapter_hash('hello')
        h2 = EmotionService.get_chapter_hash('world')
        assert h1 != h2

    def test_empty_input(self):
        h = EmotionService.get_chapter_hash('')
        assert len(h) == 32

    def test_matches_md5(self):
        expected = hashlib.md5('test'.encode()).hexdigest()
        assert EmotionService.get_chapter_hash('test') == expected
