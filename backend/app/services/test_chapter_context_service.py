# Test chapter_context_service dataclass
from app.services.chapter_context_service import ChapterRAGContext
from app.services.vector_store_service import RetrievedChunk, RetrievedSummary

class TestRetrievedChunk:
    def test_create_retrieved_chunk(self):
        c = RetrievedChunk(
            content='The hero faced their greatest fear.',
            chapter_number=5,
            chapter_title='The Turning Point',
            score=0.85,
            metadata={'source': 'ch5'},
        )
        assert c.chapter_number == 5
        assert c.score == 0.85
        assert c.metadata['source'] == 'ch5'

class TestRetrievedSummary:
    def test_create_summary(self):
        s = RetrievedSummary(
            chapter_number=3,
            title='Opening Gambit',
            summary='The hero enters the city.',
            score=0.72,
        )
        assert s.chapter_number == 3
        assert s.score == 0.72

class TestChapterRAGContext:
    def test_empty_context(self):
        ctx = ChapterRAGContext(query='test', chunks=[], summaries=[])
        assert ctx.query == 'test'
        assert ctx.chunk_texts() == []

    def test_chunk_without_title(self):
        c = RetrievedChunk(content='Content', chapter_number=3, chapter_title=None, score=0.9, metadata={})
        ctx = ChapterRAGContext(query='test', chunks=[c], summaries=[])
        texts = ctx.chunk_texts()
        assert len(texts) == 1
        assert '第3章' in texts[0]

    def test_chunk_with_title(self):
        c = RetrievedChunk(content='It begins.', chapter_number=1, chapter_title='Prologue', score=1.0, metadata={})
        ctx = ChapterRAGContext(query='test', chunks=[c], summaries=[])
        texts = ctx.chunk_texts()
        assert 'Prologue' in texts[0]
