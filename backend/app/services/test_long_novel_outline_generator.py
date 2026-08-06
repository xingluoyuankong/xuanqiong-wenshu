"""Tests for LongNovelOutlineGenerator — multi-volume outline generation."""
import pytest
from unittest.mock import AsyncMock
from app.services.long_novel_outline_generator import LongNovelOutlineGenerator


class TestLongNovelOutlineGenerator:

    @pytest.mark.asyncio
    async def test_generate_outline__valid_json(self):
        mock_llm = AsyncMock()
        mock_llm.get_llm_response = AsyncMock(return_value='{"novel_title":"T","volumes":[{"volume_number":1,"volume_title":"V1","chapters":[{"chapter_number":1,"title":"C1","summary":"S"}]}]}')
        gen = LongNovelOutlineGenerator(llm_service=mock_llm)
        result = await gen.generate_outline(
            blueprint_data={"title": "T"}, llm_service=mock_llm, user_id=0, volume_count=2, chapters_per_volume=5,
        )
        assert result is not None
        # Output is always a dict containing the enriched data
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self):
        mock_llm = AsyncMock()
        mock_llm.get_llm_response = AsyncMock(return_value="not json!!!")
        gen = LongNovelOutlineGenerator(llm_service=mock_llm)
        result = await gen.generate_outline(
            blueprint_data={"title":"F"}, llm_service=mock_llm, user_id=0, volume_count=1, chapters_per_volume=5,
        )
        assert result is not None
        assert isinstance(result, dict)

    def test_estimate_structure(self):
        s = LongNovelOutlineGenerator.estimate_structure(500000, "奇幻")
        assert s is not None
        assert s["total_chapters"] > 0

    def test_flatten_outline(self):
        data = {"volumes": [{"volume_number": 1, "chapters": [{"chapter_number": 1, "title": "序", "summary": "..."}]}]}
        flat = LongNovelOutlineGenerator.flatten_outline(data)
        assert len(flat) == 1
