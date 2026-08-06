"""enrichment_service core tests"""
import pytest
from unittest.mock import AsyncMock
from app.services.enrichment_service import EnrichmentService, EnrichmentResult
from app.services.llm_service import LLMService

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_llm():
    m = AsyncMock(spec=LLMService)
    m.generate_chat_completion = AsyncMock()
    return m

@pytest.fixture
def enrichment_service(mock_db, mock_llm):
    return EnrichmentService(mock_db, mock_llm)

async def test_short_text_handled_gracefully(enrichment_service):
    """Short text should return None or EnrichmentResult without crashing."""
    r = await enrichment_service.check_and_enrich(
        chapter_text="Very short.",
        target_word_count=2000,
        user_id=1,
        threshold=0.5,
    )
    if r is not None:
        assert isinstance(r, EnrichmentResult)
        assert r.word_count_before >= 0
    # Either None (quality gate rejected) or EnrichmentResult is acceptable


async def test_context_param_accepted(enrichment_service):
    """Confirm context dict param is accepted without errors."""
    r = await enrichment_service.check_and_enrich(
        chapter_text="Test content with context for enrichment.",
        user_id=1,
        target_word_count=200,
        threshold=2.0,
        context={"previous_summary": "Previously on..."},
    )
    if r is not None:
        assert isinstance(r.chapter_text, str)
