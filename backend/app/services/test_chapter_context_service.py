import pytest

from app.services import chapter_context_service as module
from app.services.chapter_context_service import ChapterContextService


class _LLM:
    def __init__(self, embedding):
        self.embedding = embedding

    async def get_embedding(self, _query, *, user_id):
        return self.embedding


class _VectorStore:
    async def query_chunks(self, **_kwargs):
        return []

    async def query_summaries(self, **_kwargs):
        return []


@pytest.mark.anyio
async def test_empty_embedding_is_explicitly_marked_degraded(monkeypatch):
    monkeypatch.setattr(module, "settings", type("SettingsStub", (), {"vector_store_enabled": True})())
    context = await ChapterContextService(
        llm_service=_LLM([]), vector_store=_VectorStore()
    ).retrieve_for_generation(
        project_id="p1", query_text="query", user_id=1
    )
    assert context.chunks == []
    assert context.summaries == []
    assert context.degraded is True
    assert context.degradation_reason == "EMBEDDING_UNAVAILABLE"


@pytest.mark.anyio
async def test_disabled_vector_store_is_not_reported_as_embedding_degradation(monkeypatch):
    monkeypatch.setattr(module, "settings", type("SettingsStub", (), {"vector_store_enabled": False})())
    context = await ChapterContextService(
        llm_service=_LLM([]), vector_store=None
    ).retrieve_for_generation(
        project_id="p1", query_text="query", user_id=1
    )
    assert context.degraded is False
    assert context.degradation_reason is None