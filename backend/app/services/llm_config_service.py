# AIMETA P=LLM配置服务_模型配置业务逻辑|R=配置管理_模型选择|NR=不含模型调用|E=LLMConfigService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
import logging
import json
from datetime import datetime, timezone
from time import perf_counter
from typing import Optional, List
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from ..models import LLMConfig
from ..repositories.llm_config_repository import LLMConfigRepository
from ..schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigRead,
    LLMProviderProfile,
    LLMProviderProfileRead,
    LLMProfileItem,
    LLMProfileItemRead,
    LLMProviderKeyHealth,
    LLMProviderHealth,
    LLMHealthCheckResponse,
    LLMAutoSwitchResponse,
)


logger = logging.getLogger(__name__)


class LLMConfigService:
    """用户自定义 LLM 配置服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = LLMConfigRepository(session)

    def _identify_provider(self, base_url: Optional[str]) -> str:
        """根据 base_url 识别 LLM 提供商"""
        if not base_url:
            return "openai"

        url_lower = base_url.lower()
        parsed = urlparse(url_lower)
        host = parsed.netloc or parsed.path

        # 识别常见提供商
        if "openai.com" in host or "api.openai.com" in host:
            return "openai"
        elif "localhost:11434" in host or "127.0.0.1:11434" in host or ":11434" in host:
            return "ollama"
        elif "anthropic.com" in host or "api.anthropic.com" in host:
            return "anthropic"
        elif "generativelanguage.googleapis.com" in host or "google" in host:
            return "google"
        elif "azure" in host:
            return "azure"
        elif "cohere" in host:
            return "cohere"
        elif "together" in host or "together.ai" in host:
            return "together"
        elif "deepseek" in host:
            return "deepseek"
        elif "moonshot" in host:
            return "moonshot"
        elif "zhipu" in host or "bigmodel.cn" in host:
            return "zhipu"
        elif "baidu" in host or "qianfan" in host:
            return "baidu"
        else:
            # 默认使用 OpenAI-like API
            return "openai-like"

    def _build_url(self, base_url: Optional[str], default_url: str, path_suffix: str) -> str:
        """统一的 URL 构建逻辑，避免路径重复"""
        if base_url:
            url = base_url.rstrip('/')
            # 如果 URL 已经包含路径后缀，则直接使用
            if not url.endswith(path_suffix):
                url += path_suffix
        else:
            url = default_url
        return url

    @staticmethod
    def _sort_model_ids(model_ids: List[str]) -> List[str]:
        def _priority(model_id: str) -> tuple[int, str]:
            lowered = (model_id or "").lower()
            if any(token in lowered for token in (":free", "/free", "-free", "free-")):
                return (0, lowered)
            if any(token in lowered for token in ("flash", "mini", "nano", "small", "haiku")):
                return (1, lowered)
            if any(token in lowered for token in ("opus", "sonnet", "gpt-5", "gpt-4", "o1", "r1", "reasoning", "pro")):
                return (3, lowered)
            return (2, lowered)

        normalized = sorted({item.strip() for item in model_ids if item and item.strip()}, key=_priority)
        return normalized

    @staticmethod
    def _sanitize_profiles(profiles: Optional[List[LLMProviderProfile | dict]]) -> List[LLMProviderProfile]:
        if not profiles:
            return []

        sanitized: List[LLMProviderProfile] = []
        for idx, raw_profile in enumerate(profiles):
            profile = (
                LLMProviderProfile.model_validate(raw_profile)
                if isinstance(raw_profile, dict)
                else raw_profile
            )
            profile_id = (profile.id or f"profile-{idx + 1}").strip() or f"profile-{idx + 1}"
            profile_name = (profile.name or f"配置组 {idx + 1}").strip() or f"配置组 {idx + 1}"
            base_url = (profile.llm_provider_url or "").strip() or None

            api_keys: List[LLMProfileItem] = []
            for item in profile.api_keys or []:
                value = (item.value or "").strip()
                if not value:
                    continue
                api_keys.append(LLMProfileItem(value=value, enabled=bool(item.enabled)))

            models: List[LLMProfileItem] = []
            for item in profile.models or []:
                value = (item.value or "").strip()
                if not value:
                    continue
                models.append(LLMProfileItem(value=value, enabled=bool(item.enabled)))

            sanitized.append(
                LLMProviderProfile(
                    id=profile_id,
                    name=profile_name,
                    enabled=bool(profile.enabled),
                    llm_provider_url=base_url,
                    api_keys=api_keys,
                    models=models,
                )
            )

        return sanitized

    @staticmethod
    def _serialize_profiles(profiles: List[LLMProviderProfile]) -> str:
        return json.dumps(
            [profile.model_dump(mode="json", exclude={"api_keys": {"__all__": {"retain_existing"}}}) for profile in profiles],
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_profiles(raw_profiles: Optional[str]) -> List[LLMProviderProfile]:
        if not raw_profiles:
            return []
        try:
            payload = json.loads(raw_profiles)
            if not isinstance(payload, list):
                return []
            parsed: List[LLMProviderProfile] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                parsed.append(LLMProviderProfile.model_validate(item))
            return parsed
        except Exception:
            logger.warning("解析 llm_provider_profiles 失败，忽略该字段")
            return []

    @staticmethod
    def _extract_primary_values_from_profiles(
        profiles: List[LLMProviderProfile],
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        active_profiles = [profile for profile in profiles if profile.enabled] or profiles
        if not active_profiles:
            return None, None, None

        primary = active_profiles[0]
        api_key_values = [item.value for item in primary.api_keys if item.enabled and item.value]
        model_values = [item.value for item in primary.models if item.enabled and item.value]
        return (
            primary.llm_provider_url,
            "\n".join(api_key_values) if api_key_values else None,
            ",".join(model_values) if model_values else None,
        )

    @staticmethod
    def _split_multivalue_text(raw_value: Optional[str], *, separator: str) -> List[str]:
        if not raw_value:
            return []
        normalized = str(raw_value).replace("，", separator)
        chunks = normalized.splitlines() if separator == "\n" else normalized.split(separator)
        return [item.strip() for item in chunks if item and item.strip()]

    def _hydrate_profiles_with_primary_fields(
        self,
        profiles: List[LLMProviderProfile],
        *,
        primary_url: Optional[str],
        primary_api_key: Optional[str],
        primary_model: Optional[str],
    ) -> List[LLMProviderProfile]:
        if not profiles:
            return profiles

        hydrated: List[LLMProviderProfile] = []
        fallback_api_keys = self._split_multivalue_text(primary_api_key, separator="\n")
        fallback_models = self._split_multivalue_text(primary_model, separator=",")

        for index, profile in enumerate(profiles):
            api_keys = list(profile.api_keys or [])
            models = list(profile.models or [])
            base_url = profile.llm_provider_url

            if index == 0:
                if not base_url and primary_url:
                    base_url = primary_url
                if not api_keys and fallback_api_keys:
                    api_keys = [LLMProfileItem(value=value, enabled=True) for value in fallback_api_keys]
                if not models and fallback_models:
                    models = [LLMProfileItem(value=value, enabled=True) for value in fallback_models]

            hydrated.append(
                LLMProviderProfile(
                    id=profile.id,
                    name=profile.name,
                    enabled=bool(profile.enabled),
                    llm_provider_url=base_url,
                    api_keys=api_keys,
                    models=models,
                )
            )

        return self._sanitize_profiles(hydrated)

    @staticmethod
    def _merge_secret_items(
        incoming_items: List[LLMProfileItem],
        stored_items: List[LLMProfileItem],
    ) -> List[LLMProfileItem]:
        merged: List[LLMProfileItem] = []
        for index, item in enumerate(incoming_items):
            value = (item.value or "").strip()
            if value:
                merged.append(LLMProfileItem(value=value, enabled=bool(item.enabled)))
                continue

            stored_value = ""
            if item.retain_existing and index < len(stored_items):
                stored_value = (stored_items[index].value or "").strip()

            if stored_value:
                merged.append(LLMProfileItem(value=stored_value, enabled=bool(item.enabled)))
        return merged

    def _merge_profiles_with_existing(
        self,
        incoming_profiles: List[LLMProviderProfile],
        stored_profiles: List[LLMProviderProfile],
    ) -> List[LLMProviderProfile]:
        stored_by_id = {
            (profile.id or "").strip(): profile
            for profile in stored_profiles
            if (profile.id or "").strip()
        }
        merged_profiles: List[LLMProviderProfile] = []
        for index, profile in enumerate(incoming_profiles):
            profile_id = (profile.id or f"profile-{index + 1}").strip() or f"profile-{index + 1}"
            stored_profile = stored_by_id.get(profile_id)
            merged_api_keys = self._merge_secret_items(
                profile.api_keys or [],
                stored_profile.api_keys if stored_profile else [],
            )
            merged_profiles.append(
                LLMProviderProfile(
                    id=profile_id,
                    name=profile.name,
                    enabled=bool(profile.enabled),
                    llm_provider_url=profile.llm_provider_url,
                    api_keys=merged_api_keys,
                    models=profile.models,
                )
            )
        return self._sanitize_profiles(merged_profiles)

    def _build_masked_profile(self, profile: LLMProviderProfile) -> LLMProviderProfileRead:
        return LLMProviderProfileRead(
            id=profile.id,
            name=profile.name,
            enabled=bool(profile.enabled),
            llm_provider_url=profile.llm_provider_url,
            api_keys=[
                LLMProfileItemRead(
                    value="",
                    enabled=bool(item.enabled),
                    masked_value=self._mask_api_key(item.value),
                    has_value=bool((item.value or "").strip()),
                    is_masked=True,
                )
                for item in (profile.api_keys or [])
                if (item.value or "").strip()
            ],
            models=[
                LLMProfileItem(value=item.value, enabled=bool(item.enabled))
                for item in (profile.models or [])
                if (item.value or "").strip()
            ],
        )

    async def upsert_config(self, user_id: int, payload: LLMConfigCreate) -> LLMConfigRead:
        instance = await self.repo.get_by_user(user_id)
        data = payload.model_dump(exclude_unset=True)

        profiles_payload = data.pop("llm_provider_profiles", None)
        sanitized_profiles = self._sanitize_profiles(profiles_payload) if profiles_payload is not None else None
        if sanitized_profiles is not None:
            stored_profiles = self._deserialize_profiles(instance.llm_provider_profiles) if instance else []
            merged_profiles = self._merge_profiles_with_existing(sanitized_profiles, stored_profiles)
            data["llm_provider_profiles"] = self._serialize_profiles(merged_profiles)
            primary_url, primary_api_key, primary_model = self._extract_primary_values_from_profiles(merged_profiles)
            data["llm_provider_url"] = primary_url
            data["llm_provider_api_key"] = primary_api_key
            data["llm_provider_model"] = primary_model

        if "llm_provider_url" in data and data["llm_provider_url"] is not None:
            data["llm_provider_url"] = str(data["llm_provider_url"])

        if instance:
            await self.repo.update_fields(instance, **data)
        else:
            instance = LLMConfig(user_id=user_id, **data)
            await self.repo.add(instance)
        await self.session.commit()
        return (await self.get_config(user_id)) or LLMConfigRead(
            user_id=user_id,
            llm_provider_url=data.get("llm_provider_url"),
            llm_provider_model=data.get("llm_provider_model"),
            llm_provider_api_key_masked=self._mask_api_key(data.get("llm_provider_api_key") or "") if data.get("llm_provider_api_key") else None,
            llm_provider_api_key_configured=bool(data.get("llm_provider_api_key")),
            llm_provider_profiles=[],
        )

    async def get_config(self, user_id: int) -> Optional[LLMConfigRead]:
        instance = await self.repo.get_by_user(user_id)
        if not instance:
            return None

        parsed_profiles = self._deserialize_profiles(instance.llm_provider_profiles)
        parsed_profiles = self._hydrate_profiles_with_primary_fields(
            parsed_profiles,
            primary_url=instance.llm_provider_url,
            primary_api_key=instance.llm_provider_api_key,
            primary_model=instance.llm_provider_model,
        )
        if not parsed_profiles and (instance.llm_provider_url or instance.llm_provider_api_key or instance.llm_provider_model):
            # 兼容旧数据：自动映射为一个默认配置组
            fallback_profile = LLMProviderProfile(
                id="legacy-default",
                name="默认配置",
                enabled=True,
                llm_provider_url=instance.llm_provider_url,
                api_keys=[
                    LLMProfileItem(value=item.strip(), enabled=True)
                    for item in (instance.llm_provider_api_key or "").splitlines()
                    if item.strip()
                ],
                models=[
                    LLMProfileItem(value=item.strip(), enabled=True)
                    for item in str(instance.llm_provider_model or "").replace("，", ",").split(",")
                    if item.strip()
                ],
            )
            parsed_profiles = [fallback_profile]

        masked_profiles = [self._build_masked_profile(profile) for profile in parsed_profiles]
        primary_masked_key = self._mask_api_key(instance.llm_provider_api_key or "") if instance.llm_provider_api_key else None
        return LLMConfigRead(
            user_id=instance.user_id,
            llm_provider_url=instance.llm_provider_url,
            llm_provider_model=instance.llm_provider_model,
            llm_provider_api_key_masked=primary_masked_key,
            llm_provider_api_key_configured=bool(instance.llm_provider_api_key),
            llm_provider_profiles=masked_profiles,
        )

    @staticmethod
    def _mask_api_key(api_key: str) -> str:
        key = (api_key or "").strip()
        if not key:
            return "<empty>"
        if len(key) <= 10:
            return "***"
        return f"{key[:6]}...{key[-4:]}"

    @staticmethod
    def _pick_current_profile(
        profiles: List[LLMProviderProfile],
    ) -> Optional[LLMProviderProfile]:
        if not profiles:
            return None
        return next((profile for profile in profiles if profile.enabled), profiles[0])

    async def _get_raw_profiles_for_runtime(self, user_id: int) -> List[LLMProviderProfile]:
        instance = await self.repo.get_by_user(user_id)
        if not instance:
            return []

        parsed_profiles = self._deserialize_profiles(instance.llm_provider_profiles)
        parsed_profiles = self._hydrate_profiles_with_primary_fields(
            parsed_profiles,
            primary_url=instance.llm_provider_url,
            primary_api_key=instance.llm_provider_api_key,
            primary_model=instance.llm_provider_model,
        )
        if parsed_profiles:
            return parsed_profiles

        if instance.llm_provider_url or instance.llm_provider_api_key or instance.llm_provider_model:
            fallback_profile = LLMProviderProfile(
                id="legacy-default",
                name="默认配置",
                enabled=True,
                llm_provider_url=instance.llm_provider_url,
                api_keys=[
                    LLMProfileItem(value=item.strip(), enabled=True)
                    for item in (instance.llm_provider_api_key or "").splitlines()
                    if item.strip()
                ],
                models=[
                    LLMProfileItem(value=item.strip(), enabled=True)
                    for item in str(instance.llm_provider_model or "").replace("，", ",").split(",")
                    if item.strip()
                ],
            )
            return self._sanitize_profiles([fallback_profile])

        return []

    async def _probe_models_endpoint(
        self,
        base_url: Optional[str],
        api_key: str,
    ) -> tuple[bool, bool, Optional[int], str]:
        url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=6.0)) as client:
                response = await client.get(url, headers=headers)

            status_code = response.status_code
            if status_code == 200:
                try:
                    payload = response.json()
                except Exception:
                    payload = {}
                models = payload.get("data", []) if isinstance(payload, dict) else []
                model_count = len(models) if isinstance(models, list) else 0
                if model_count > 0:
                    return True, True, status_code, f"models 接口可用，返回 {model_count} 个模型"
                return True, False, status_code, "models 接口返回成功，但未返回模型"

            if status_code in (401, 403):
                return True, False, status_code, "鉴权失败，请检查 API Key"
            if status_code == 429:
                return True, False, status_code, "请求被限流或额度不足"
            if status_code >= 500:
                return True, False, status_code, f"Provider 服务异常（HTTP {status_code}）"
            return True, False, status_code, f"models 接口返回 HTTP {status_code}"
        except httpx.ConnectError:
            return False, False, None, "连接失败，无法访问 Provider"
        except httpx.ReadError:
            return False, False, None, "读取响应失败，连接被中断"
        except httpx.TimeoutException:
            return False, False, None, "请求超时"
        except Exception as exc:
            return False, False, None, f"探测异常：{exc}"

    async def _probe_key_health(
        self,
        base_url: Optional[str],
        api_key: str,
        key_index: int,
        enabled: bool,
    ) -> LLMProviderKeyHealth:
        started = perf_counter()
        model_count = 0
        status_code: Optional[int] = None
        detail: Optional[str] = None
        reachable = False
        usable = False

        try:
            models = await self.get_available_models(api_key=api_key, base_url=base_url)
            model_count = len(models)
            if model_count > 0:
                reachable = True
                usable = True
                detail = f"可用，拉取到 {model_count} 个模型"
            else:
                reachable, usable, status_code, detail = await self._probe_models_endpoint(base_url, api_key)
        except Exception as exc:
            detail = f"探测失败：{exc}"

        latency_ms = int((perf_counter() - started) * 1000)
        return LLMProviderKeyHealth(
            key_index=key_index,
            key_mask=self._mask_api_key(api_key),
            enabled=enabled,
            reachable=reachable,
            usable=usable,
            model_count=model_count,
            status_code=status_code,
            latency_ms=latency_ms,
            detail=detail,
        )

    async def _build_profile_health(self, profile: LLMProviderProfile) -> LLMProviderHealth:
        all_keys: List[tuple[int, str, bool]] = []
        for index, key_item in enumerate(profile.api_keys or [], start=1):
            value = (key_item.value or "").strip()
            if not value:
                continue
            all_keys.append((index, value, bool(key_item.enabled)))

        if not all_keys:
            return LLMProviderHealth(
                profile_id=profile.id or "",
                profile_name=(profile.name or profile.id or "未命名配置组"),
                enabled=bool(profile.enabled),
                llm_provider_url=profile.llm_provider_url,
                status="no_key",
                summary="未配置可用 API Key",
                reachable=False,
                usable=False,
                model_count=0,
                checked_key_count=0,
                keys=[],
            )

        keys_to_check = [item for item in all_keys if item[2]] or all_keys
        key_results: List[LLMProviderKeyHealth] = []
        for key_index, key_value, key_enabled in keys_to_check:
            key_results.append(
                await self._probe_key_health(
                    base_url=profile.llm_provider_url,
                    api_key=key_value,
                    key_index=key_index,
                    enabled=key_enabled,
                )
            )

        profile_usable = any(item.usable for item in key_results)
        profile_reachable = any(item.reachable for item in key_results)
        model_count = max((item.model_count for item in key_results), default=0)

        if profile_usable:
            status = "healthy"
            summary = "可用，可正常请求模型服务"
        elif profile_reachable:
            status = "degraded"
            summary = "可达但不可用（通常是 Key、配额或限流问题）"
        else:
            status = "down"
            summary = "不可达（网络或 Provider 连接异常）"

        return LLMProviderHealth(
            profile_id=profile.id or "",
            profile_name=(profile.name or profile.id or "未命名配置组"),
            enabled=bool(profile.enabled),
            llm_provider_url=profile.llm_provider_url,
            status=status,
            summary=summary,
            reachable=profile_reachable,
            usable=profile_usable,
            model_count=model_count,
            checked_key_count=len(key_results),
            keys=key_results,
        )

    async def run_health_check(
        self,
        user_id: int,
        include_disabled: bool = True,
    ) -> LLMHealthCheckResponse:
        config = await self.get_config(user_id)
        if not config:
            return LLMHealthCheckResponse(
                checked_at=datetime.now(timezone.utc),
                overall_status="down",
                has_usable_profile=False,
                recommended_profile_id=None,
                recommended_profile_name=None,
                current_profile_id=None,
                current_profile_name=None,
                recommended_action="当前还没有保存任何 LLM 配置，请先新增并保存配置组。",
                profiles=[],
            )

        profiles = await self._get_raw_profiles_for_runtime(user_id)
        current_profile = self._pick_current_profile(profiles)
        if not profiles:
            return LLMHealthCheckResponse(
                checked_at=datetime.now(timezone.utc),
                overall_status="down",
                has_usable_profile=False,
                recommended_profile_id=None,
                recommended_profile_name=None,
                current_profile_id=current_profile.id if current_profile else None,
                current_profile_name=current_profile.name if current_profile else None,
                recommended_action="当前配置里还没有可检查的配置组，请先补充并保存。",
                profiles=[],
            )

        candidate_profiles = profiles if include_disabled else [profile for profile in profiles if profile.enabled]
        profile_results: List[LLMProviderHealth] = []
        for profile in candidate_profiles:
            profile_results.append(await self._build_profile_health(profile))

        usable_profiles = [item for item in profile_results if item.usable]
        preferred_profile = next((item for item in usable_profiles if item.enabled), None)
        if not preferred_profile and usable_profiles:
            preferred_profile = usable_profiles[0]

        if not usable_profiles:
            overall_status = "down"
        elif any(item.enabled and not item.usable for item in profile_results):
            overall_status = "degraded"
        else:
            overall_status = "ok"

        current_profile_usable: Optional[bool] = None
        if current_profile:
            current_result = next(
                (item for item in profile_results if item.profile_id == current_profile.id),
                None,
            )
            current_profile_usable = bool(current_result and current_result.usable)

        if not usable_profiles:
            recommended_action = "未发现可用 Provider，请先修复网络、API Key 或额度问题。"
        elif current_profile_usable:
            recommended_action = "当前激活配置可用，无需切换。"
        elif preferred_profile:
            recommended_action = f"建议切换到可用配置组：{preferred_profile.profile_name}"
        else:
            recommended_action = "存在可用配置组，建议执行自动切换。"

        return LLMHealthCheckResponse(
            checked_at=datetime.now(timezone.utc),
            overall_status=overall_status,
            has_usable_profile=bool(usable_profiles),
            recommended_profile_id=preferred_profile.profile_id if preferred_profile else None,
            recommended_profile_name=preferred_profile.profile_name if preferred_profile else None,
            current_profile_id=current_profile.id if current_profile else None,
            current_profile_name=current_profile.name if current_profile else None,
            current_profile_usable=current_profile_usable,
            recommended_action=recommended_action,
            profiles=profile_results,
        )

    async def auto_switch_provider(self, user_id: int) -> LLMAutoSwitchResponse:
        config = await self.get_config(user_id)
        if not config:
            health = await self.run_health_check(user_id=user_id, include_disabled=True)
            return LLMAutoSwitchResponse(
                switched=False,
                reason="未找到 LLM 配置，请先保存配置组",
                switch_basis="no_config",
                previous_profile_id=None,
                previous_profile_name=None,
                active_profile_id=None,
                active_profile_name=None,
                health=health,
                config=None,
            )

        profiles = await self._get_raw_profiles_for_runtime(user_id)
        current_profile = self._pick_current_profile(profiles)
        health = await self.run_health_check(user_id=user_id, include_disabled=True)
        recommended_id = health.recommended_profile_id

        if not recommended_id:
            return LLMAutoSwitchResponse(
                switched=False,
                switch_basis="no_usable_provider",
                reason="未探测到可用 Provider，请先修复网络或 API Key",
                previous_profile_id=current_profile.id if current_profile else None,
                previous_profile_name=current_profile.name if current_profile else None,
                active_profile_id=current_profile.id if current_profile else None,
                active_profile_name=current_profile.name if current_profile else None,
                health=health,
                config=config,
            )

        if current_profile and current_profile.id == recommended_id and current_profile.enabled:
            return LLMAutoSwitchResponse(
                switched=False,
                switch_basis="current_profile_usable",
                reason="当前启用的 Provider 已可用，无需切换",
                previous_profile_id=current_profile.id,
                previous_profile_name=current_profile.name,
                active_profile_id=current_profile.id,
                active_profile_name=current_profile.name,
                health=health,
                config=config,
            )

        target_profile = next((profile for profile in profiles if profile.id == recommended_id), None)
        if not target_profile:
            return LLMAutoSwitchResponse(
                switched=False,
                switch_basis="recommended_profile_missing",
                reason="推荐 Provider 不在当前配置中，自动切换已跳过",
                previous_profile_id=current_profile.id if current_profile else None,
                previous_profile_name=current_profile.name if current_profile else None,
                active_profile_id=current_profile.id if current_profile else None,
                active_profile_name=current_profile.name if current_profile else None,
                health=health,
                config=config,
            )

        updated_target = target_profile.model_copy(deep=True)
        updated_target.enabled = True
        remaining_profiles = []
        for profile in profiles:
            if profile.id == recommended_id:
                continue
            copied = profile.model_copy(deep=True)
            copied.enabled = False
            remaining_profiles.append(copied)
        reordered_profiles = [updated_target] + remaining_profiles

        saved_config = await self.upsert_config(
            user_id=user_id,
            payload=LLMConfigCreate(llm_provider_profiles=reordered_profiles),
        )
        updated_health = await self.run_health_check(user_id=user_id, include_disabled=True)

        return LLMAutoSwitchResponse(
            switched=True,
            switch_basis="recommended_profile_healthiest",
            reason=f"已切换到可用 Provider：{updated_target.name or updated_target.id}",
            previous_profile_id=current_profile.id if current_profile else None,
            previous_profile_name=current_profile.name if current_profile else None,
            active_profile_id=updated_target.id,
            active_profile_name=updated_target.name,
            health=updated_health,
            config=saved_config,
        )

    async def delete_config(self, user_id: int) -> bool:
        instance = await self.repo.get_by_user(user_id)
        if not instance:
            return False
        await self.repo.delete(instance)
        await self.session.commit()
        return True

    async def get_available_models(
        self, api_key: str, base_url: Optional[str] = None
    ) -> List[str]:
        """使用指定的凭证获取可用的模型列表"""
        # 识别提供商
        provider = self._identify_provider(base_url)
        logger.info("识别到 LLM 提供商: %s (base_url: %s)", provider, base_url)

        # Ollama 不需要 API Key
        if provider == "ollama":
            return await self._get_ollama_models(base_url)

        api_key = (api_key or "").strip()
        if not api_key:
            logger.warning("获取模型列表失败：未提供 API Key")
            raise ValueError("未提供 API Key")

        try:
            # 根据不同提供商获取模型列表
            if provider == "anthropic":
                models = await self._get_anthropic_models(api_key, base_url)
            elif provider == "google":
                models = await self._get_google_models(api_key, base_url)
            elif provider == "azure":
                models = await self._get_azure_models(api_key, base_url)
            elif provider == "cohere":
                models = await self._get_cohere_models(api_key, base_url)
            else:
                # OpenAI 和 OpenAI-like (包括 together, deepseek, moonshot, zhipu 等)
                models = await self._get_openai_like_models(api_key, base_url)
            return self._sort_model_ids(models)
        except Exception as e:
            error_msg = str(e)
            logger.error("获取模型列表失败: provider=%s, error=%s", provider, error_msg, exc_info=True)

            # 提供更友好的错误信息
            if "Connection error" in error_msg or "disconnected" in error_msg.lower():
                logger.warning("连接错误，可能是 API URL 配置错误或网络问题")
            elif "401" in error_msg or "Unauthorized" in error_msg:
                logger.warning("认证失败，请检查 API Key 是否正确")
            elif "404" in error_msg or "Not Found" in error_msg:
                logger.warning("API 端点不存在，请检查 URL 是否正确")

            raise RuntimeError(error_msg) from e

    async def _get_openai_like_models(self, api_key: str, base_url: Optional[str]) -> List[str]:
        """获取 OpenAI 或 OpenAI-like API 的模型列表"""
        import httpx
        from openai import APIConnectionError, APIError

        try:
            # 创建带有超时和重试配置的客户端
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=httpx.Timeout(30.0, connect=10.0),
                max_retries=2,
            )

            logger.info("尝试获取模型列表: base_url=%s", base_url)
            models_response = await client.models.list()
            model_ids = [model.id for model in models_response.data]
            logger.info("成功获取 %d 个 OpenAI-like 模型", len(model_ids))
            return sorted(model_ids)

        except APIConnectionError as e:
            logger.error("API 连接错误: %s", str(e), exc_info=True)
            # 某些自建服务可能不支持 /v1/models 端点，尝试使用 httpx 直接请求
            return await self._get_models_via_http(api_key, base_url)

        except APIError as e:
            logger.error("API 调用错误: status_code=%s, message=%s", getattr(e, 'status_code', 'unknown'), str(e))
            return await self._get_models_via_http(api_key, base_url)

        except Exception as e:
            logger.error("获取 OpenAI-like 模型列表失败: %s", str(e), exc_info=True)
            return await self._get_models_via_http(api_key, base_url)

    async def _get_models_via_http(self, api_key: str, base_url: Optional[str]) -> List[str]:
        """使用 httpx 直接请求模型列表（备选方案）"""
        import httpx

        try:
            # 构建完整的 URL
            if base_url:
                url = base_url.rstrip('/') + '/models'
            else:
                url = 'https://api.openai.com/v1/models'

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            logger.info("使用 HTTP 直接请求模型列表: url=%s", url)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

                logger.info("HTTP 响应状态码: %d", response.status_code)

                if response.status_code == 200:
                    data = response.json()
                    models = data.get('data', [])
                    model_ids = [model.get('id') for model in models if model.get('id')]
                    logger.info("通过 HTTP 成功获取 %d 个模型", len(model_ids))
                    return sorted(model_ids)
                elif response.status_code == 404:
                    logger.warning("模型列表端点不存在 (404)，该服务可能不支持模型列表查询")
                    return []
                elif response.status_code == 401:
                    logger.warning("认证失败 (401)，请检查 API Key 是否正确")
                    return []
                else:
                    logger.warning("HTTP 请求失败: status=%d, body=%s", response.status_code, response.text[:200])
                    return []

        except httpx.TimeoutException:
            logger.error("HTTP 请求超时")
            return []
        except httpx.ConnectError as e:
            logger.error("无法连接到服务器: %s", str(e))
            return []
        except Exception as e:
            logger.error("HTTP 请求失败: %s", str(e), exc_info=True)
            return []

    async def _get_anthropic_models(self, api_key: str, base_url: Optional[str]) -> List[str]:
        """获取 Anthropic 的模型列表"""
        # Anthropic 目前不提供模型列表 API，返回常用模型
        logger.info("返回 Anthropic 预定义模型列表")
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]

    async def _get_google_models(self, api_key: str, base_url: Optional[str]) -> List[str]:
        """获取 Google Gemini 的模型列表"""
        import httpx

        try:
            # 使用统一的 URL 构建方法
            url = self._build_url(
                base_url,
                "https://generativelanguage.googleapis.com/v1beta",
                "/v1beta"
            )
            url += f"/models?key={api_key}"

            logger.info("请求 Google 模型列表: url=%s", url.replace(api_key, "***"))

            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)

                logger.info("HTTP 响应状态码: %d", response.status_code)
                response.raise_for_status()
                data = response.json()

                model_ids = []
                for model in data.get("models", []):
                    model_name = model.get("name", "")
                    # 移除 "models/" 前缀
                    if model_name.startswith("models/"):
                        model_name = model_name[7:]
                    # 只返回生成模型（非 embedding 模型）
                    if "generateContent" in model.get("supportedGenerationMethods", []):
                        model_ids.append(model_name)

                logger.info("成功获取 %d 个 Google 模型", len(model_ids))
                return sorted(model_ids)
        except httpx.HTTPStatusError as e:
            logger.error("Google API HTTP 错误: status=%d, message=%s", e.response.status_code, str(e))
            # 返回常用的 Gemini 模型作为备选
            return [
                "gemini-2.0-flash-exp",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.0-pro",
            ]
        except httpx.TimeoutException:
            logger.error("Google API 请求超时")
            return [
                "gemini-2.0-flash-exp",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.0-pro",
            ]
        except Exception as e:
            logger.error("获取 Google 模型列表失败: %s", str(e), exc_info=True)
            # 返回常用的 Gemini 模型作为备选
            return [
                "gemini-2.0-flash-exp",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-1.0-pro",
            ]

    async def _get_azure_models(self, api_key: str, base_url: Optional[str]) -> List[str]:
        """获取 Azure OpenAI 的模型列表"""
        # Azure OpenAI 的部署是用户自定义的，无法直接列举
        # 返回常见的 Azure OpenAI 模型名称
        logger.info("返回 Azure OpenAI 预定义模型列表")
        return [
            "gpt-4",
            "gpt-4-32k",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-35-turbo",
            "gpt-35-turbo-16k",
        ]

    async def _get_cohere_models(self, api_key: str, base_url: Optional[str]) -> List[str]:
        """获取 Cohere 的模型列表"""
        import httpx

        try:
            # 使用统一的 URL 构建方法
            url = self._build_url(
                base_url,
                "https://api.cohere.ai/v1",
                "/v1"
            )
            url += "/models"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            logger.info("请求 Cohere 模型列表: url=%s", url)

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=30.0)

                logger.info("HTTP 响应状态码: %d", response.status_code)
                response.raise_for_status()
                data = response.json()

                model_ids = [model.get("name") for model in data.get("models", []) if model.get("name")]
                logger.info("成功获取 %d 个 Cohere 模型", len(model_ids))
                return sorted(model_ids)
        except httpx.HTTPStatusError as e:
            logger.error("Cohere API HTTP 错误: status=%d, message=%s", e.response.status_code, str(e))
            return [
                "command-r-plus",
                "command-r",
                "command",
                "command-light",
            ]
        except httpx.TimeoutException:
            logger.error("Cohere API 请求超时")
            return [
                "command-r-plus",
                "command-r",
                "command",
                "command-light",
            ]
        except Exception as e:
            logger.error("获取 Cohere 模型列表失败: %s", str(e), exc_info=True)
            # 返回常用的 Cohere 模型作为备选
            return [
                "command-r-plus",
                "command-r",
                "command",
                "command-light",
            ]

    async def _get_ollama_models(self, base_url: Optional[str]) -> List[str]:
        """获取 Ollama 本地模型列表"""
        import httpx

        # Ollama 默认地址
        url = (base_url or "http://localhost:11434/v1").rstrip("/")
        # 使用 Ollama 原生 API 获取模型列表
        api_url = url.replace("/v1", "") + "/api/tags"

        logger.info("请求 Ollama 模型列表: url=%s", api_url)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api_url)

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    model_ids = [model.get("name", "") for model in models if model.get("name")]
                    logger.info("成功获取 %d 个 Ollama 模型: %s", len(model_ids), model_ids)
                    return sorted(model_ids)
                else:
                    logger.warning("Ollama API 返回非 200 状态: %d", response.status_code)
                    return []
        except httpx.ConnectError:
            logger.error("无法连接到 Ollama 服务，请确认 Ollama 已启动 (ollama serve)")
            return []
        except httpx.TimeoutException:
            logger.error("Ollama API 请求超时")
            return []
        except Exception as e:
            logger.error("获取 Ollama 模型列表失败: %s", str(e), exc_info=True)
            return []
