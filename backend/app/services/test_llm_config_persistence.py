from app.models.user import User
from app.schemas.llm_config import LLMConfigCreate
from app.services.llm_config_service import LLMConfigService


async def test_llm_config_version_is_persisted_and_stable_across_service_instances(task_session):
    task_session.add(User(id=901, username="config-version-user", hashed_password="x"))
    await task_session.commit()
    service = LLMConfigService(task_session)

    saved = await service.upsert_config(
        901,
        LLMConfigCreate(
            llm_provider_url="https://provider.example/v1",
            llm_provider_api_key="secret-one",
            llm_provider_model="model-a",
        ),
    )
    reread = await LLMConfigService(task_session).get_config(901)
    assert saved.version > 0
    assert reread is not None
    assert reread.version == saved.version
    assert reread.llm_provider_model == "model-a"

    changed = await service.upsert_config(
        901,
        LLMConfigCreate(
            llm_provider_url="https://provider.example/v1",
            llm_provider_api_key="secret-two",
            llm_provider_model="model-b",
        ),
    )
    assert changed.version != saved.version


async def test_masked_profile_key_is_retained_when_other_fields_are_saved(task_session):
    task_session.add(User(id=902, username="config-retain-user", hashed_password="x"))
    await task_session.commit()
    service = LLMConfigService(task_session)

    first = await service.upsert_config(
        902,
        LLMConfigCreate(
            llm_provider_profiles=[
                {
                    "id": "main",
                    "name": "主配置",
                    "enabled": True,
                    "llm_provider_url": "https://provider.example/v1",
                    "api_keys": [{"value": "secret-one", "enabled": True}],
                    "models": [{"value": "model-a", "enabled": True}],
                }
            ]
        ),
    )
    assert first.llm_provider_api_key_configured is True

    second = await service.upsert_config(
        902,
        LLMConfigCreate(
            llm_provider_profiles=[
                {
                    "id": "main",
                    "name": "主配置已改名",
                    "enabled": True,
                    "llm_provider_url": "https://provider.example/v2",
                    "api_keys": [
                        {"value": "", "enabled": True, "retain_existing": True}
                    ],
                    "models": [{"value": "model-b", "enabled": True}],
                }
            ]
        ),
    )
    assert second.llm_provider_api_key_configured is True
    assert second.llm_provider_url == "https://provider.example/v2"
    assert second.llm_provider_model == "model-b"

    stored = await service.repo.get_by_user(902)
    assert stored is not None
    assert stored.llm_provider_api_key == "secret-one"
    assert "secret-one" in (stored.llm_provider_profiles or "")


import pytest


@pytest.mark.asyncio
async def test_health_probe_does_not_mark_models_only_as_usable(monkeypatch):
    service = LLMConfigService(None)

    async def fake_models(**kwargs):
        return ["configured-model", "other-model"]

    async def fake_chat(**kwargs):
        assert kwargs["model"] == "configured-model"
        return True, False, 500, "当前模型 chat 接口异常（HTTP 500）"

    monkeypatch.setattr(service, "get_available_models", fake_models)
    monkeypatch.setattr(service, "_probe_chat_completion", fake_chat)
    result = await service._probe_key_health(
        base_url="https://provider.example/v1",
        api_key="secret-key",
        key_index=1,
        enabled=True,
        models=["configured-model"],
    )

    assert result.reachable is True
    assert result.usable is False
    assert result.model_count == 2
    assert result.status_code == 500
    assert "secret-key" not in (result.detail or "")


@pytest.mark.asyncio
async def test_health_probe_marks_key_usable_only_after_chat_success(monkeypatch):
    service = LLMConfigService(None)

    async def fake_models(**kwargs):
        return ["configured-model"]

    async def fake_chat(**kwargs):
        return True, True, 200, "当前模型 configured-model 可完成最小 chat 请求"

    monkeypatch.setattr(service, "get_available_models", fake_models)
    monkeypatch.setattr(service, "_probe_chat_completion", fake_chat)
    result = await service._probe_key_health(
        base_url="https://provider.example/v1",
        api_key="secret-key",
        key_index=1,
        enabled=True,
        models=["configured-model"],
    )

    assert result.reachable is True
    assert result.usable is True
    assert result.status_code == 200
    assert "configured-model" in (result.detail or "")
