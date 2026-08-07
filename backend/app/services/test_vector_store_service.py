"""vector_store_service dataclass tests"""
import pytest
from app.services.vector_store_service import RetrievedChunk, RetrievedSummary

pytestmark = pytest.mark.asyncio

def test_retrieved_chunk_fields():
    c = RetrievedChunk(
        content="test chunk",
        chapter_number=1,
        chapter_title="Chapter 1",
        score=0.95,
        metadata={"source": "blueprint"},
    )
    assert c.content == "test chunk"
    assert c.chapter_number == 1
    assert c.score == 0.95
    assert c.metadata == {"source": "blueprint"}

def test_retrieved_summary_fields():
    s = RetrievedSummary(
        chapter_number=2,
        title="Chapter 2 Summary",
        summary="This is a summary.",
        score=0.88,
    )
    assert s.chapter_number == 2
    assert s.title == "Chapter 2 Summary"
    assert s.summary == "This is a summary."
    assert s.score == 0.88
