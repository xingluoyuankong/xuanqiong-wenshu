import pytest

from app.services.llm_service import LLMService

from app.services import chapter_context_service as module
from app.services.chapter_context_service import ChapterContextService


class _LLM:
    def __init__(self, embedding, status=None):
        self.embedding = embedding
        self.status = status or {}

    async def get_embedding(self, _query, *, user_id):
        return self.embedding

    def get_embedding_status(self):
        return dict(self.status)


class _VectorStore:
    async def query_chunks(self, **_kwargs):
        return []

    async def query_summaries(self, **_kwargs):
        return []


@pytest.mark.anyio
async def test_empty_embedding_is_explicitly_marked_degraded(monkeypatch):
    monkeypatch.setattr(module, "settings", type("SettingsStub", (), {"vector_store_enabled": True})())
    context = await ChapterContextService(
        llm_service=_LLM([], {"status": "degraded", "code": "EMBEDDING_AUTHENTICATION_FAILED"}), vector_store=_VectorStore()
    ).retrieve_for_generation(
        project_id="p1", query_text="query", user_id=1
    )
    assert context.chunks == []
    assert context.summaries == []
    assert context.degraded is True
    assert context.degradation_reason == "EMBEDDING_AUTHENTICATION_FAILED"
    assert context.embedding_status["status"] == "degraded"


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

@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, "EMBEDDING_AUTHENTICATION_FAILED"),
        (403, "EMBEDDING_PERMISSION_DENIED"),
        (None, "EMBEDDING_REQUEST_FAILED"),
    ],
)
def test_embedding_failure_codes_are_stable(status_code, expected):
    error = type("ProviderError", (), {"status_code": status_code})()
    assert LLMService._embedding_failure_code(error) == expected


@pytest.mark.anyio
async def test_embedding_provider_missing_key_is_classified_without_provider_call(monkeypatch):
    from app.services.llm_service import LLMService

    service = object.__new__(LLMService)
    service._embedding_status = {}

    async def config_value(key):
        return {"embedding.provider": "openai", "embedding.model": "text-embedding-3-large", "embedding.api_key": None}.get(key)

    service._get_config_value = config_value
    vector = await service.get_embedding("probe", user_id=1)
    assert vector == []
    assert service.get_embedding_status()["code"] == "EMBEDDING_CONFIG_MISSING"
