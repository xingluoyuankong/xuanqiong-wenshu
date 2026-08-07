# Test embedding_service cache key generation
from app.services.embedding_service import EmbeddingService
import hashlib

svc = EmbeddingService()

class TestCacheKey:
    def test_deterministic(self):
        k1 = svc._get_cache_key('hello')
        k2 = svc._get_cache_key('hello')
        assert k1 == k2

    def test_different_texts(self):
        k1 = svc._get_cache_key('hello')
        k2 = svc._get_cache_key('world')
        assert k1 != k2

    def test_matches_md5(self):
        expected = hashlib.md5('test'.encode()).hexdigest()
        assert svc._get_cache_key('test') == expected

    def test_empty_string(self):
        key = svc._get_cache_key('')
        assert len(key) == 32
