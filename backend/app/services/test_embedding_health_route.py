import types

import pytest

from app.api.routers import llm_config
from app.services import llm_service as llm_service_module


class _FakeLLMService:
    def __init__(self, _session):
        pass

    async def get_embedding(self, _text, *, user_id):
        return []

    def get_embedding_status(self):
        return {
            "status": "degraded",
            "provider": "openai",
            "model": "text-embedding-3-large",
            "code": "EMBEDDING_CONFIG_MISSING",
        }


@pytest.mark.anyio
async def test_embedding_health_route_returns_redacted_capability_status(monkeypatch):
    monkeypatch.setattr(llm_service_module, "LLMService", _FakeLLMService)
    result = await llm_config.embedding_health_check(
        session=object(),
        current_user=types.SimpleNamespace(id=1),
    )

    assert result["vector_nonempty"] is False
    assert result["vector_dimension"] == 0
    assert result["status"]["code"] == "EMBEDDING_CONFIG_MISSING"
    assert "api_key" not in result
    assert "token" not in result
    assert result["checked_at"].endswith("+00:00")
