# -*- coding: utf-8 -*-
# AIMETA P=LLM工具_大模型调用辅助|R=请求构建_响应解析|NR=不含业务逻辑|E=LLMTool|X=internal|A=工具类|D=httpx|S=net|RD=./README.ai
"""OpenAI 兼容型 LLM 工具封装，保持与旧项目一致的接口体验。"""

import os
from dataclasses import asdict, dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

from openai import AsyncOpenAI

from ..core.config import get_settings


def _read_env_value(*names: str) -> Optional[str]:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


class LLMClient:
    """异步流式调用封装，兼容 OpenAI SDK。"""

    _PROMPT_CACHE_KEY_UNSUPPORTED_HOSTS = {"api.xzxyuan.ccwu.cc"}

    @classmethod
    def _supports_prompt_cache_key(cls, base_url: Optional[str]) -> bool:
        host = (urlparse(str(base_url or "")).hostname or "").lower()
        return host not in cls._PROMPT_CACHE_KEY_UNSUPPORTED_HOSTS

    @classmethod
    def _sanitize_chat_payload(
        cls, payload: Dict[str, Any], *, base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        cleaned = {key: value for key, value in dict(payload).items() if value is not None}
        if not cls._supports_prompt_cache_key(base_url):
            cleaned.pop("prompt_cache_key", None)
        return cleaned

    @staticmethod
    def _resolve_model(model: Optional[str]) -> str:
        """Use the same configured default for every low-level call path."""
        return (
            (model or "").strip()
            or _read_env_value("OPENAI_MODEL_NAME", "MODEL")
            or get_settings().openai_model_name
        )

    @staticmethod
    def _build_response_format_payload(response_format: Optional[Any]) -> Optional[Dict[str, Any]]:
        if not response_format:
            return None
        if isinstance(response_format, dict):
            return response_format
        return {"type": str(response_format)}

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        key = (api_key or "").strip() or _read_env_value("OPENAI_API_KEY")
        if not key:
            raise ValueError("缺少 OPENAI_API_KEY 配置，请在数据库或环境变量中补全。")

        resolved_base_url = (base_url or "").strip() or _read_env_value("OPENAI_API_BASE_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE")
        self._base_url = resolved_base_url
        self._client = AsyncOpenAI(api_key=key, base_url=resolved_base_url)

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        response_format: Optional[Any] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, str], None]:
        payload = {
            "model": self._resolve_model(model),
            "messages": [msg.to_dict() for msg in messages],
            "stream": True,
            "timeout": timeout,
            **kwargs,
        }
        response_format_payload = self._build_response_format_payload(response_format)
        if response_format_payload:
            payload["response_format"] = response_format_payload
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload = self._sanitize_chat_payload(payload, base_url=self._base_url)

        stream = await self._client.chat.completions.create(**payload)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            reasoning_content = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
            yield {
                "content": getattr(delta, "content", None),
                "reasoning_content": reasoning_content,
                "finish_reason": choice.finish_reason,
            }

    @staticmethod
    def _coerce_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                    continue
                text = getattr(item, "text", None)
                if isinstance(text, str) and text:
                    parts.append(text)
            return "".join(parts)
        return ""


    @staticmethod
    def _extract_message_text(msg, prefer_reasoning_fallback=True):
        if isinstance(msg, dict):
            content = msg.get('content') or ''
            reasoning = msg.get('reasoning_content') or msg.get('reasoning') or ''
        else:
            content = getattr(msg, 'content', None)
            reasoning = getattr(msg, 'reasoning_content', None) or getattr(msg, 'reasoning', None) or ''
        if content:
            return content
        if prefer_reasoning_fallback and reasoning:
            return str(reasoning)
        return ''

    @staticmethod
    def _extract_reasoning_text(msg):
        if isinstance(msg, dict):
            return str(msg.get('reasoning_content') or msg.get('reasoning') or '')
        return str(getattr(msg, 'reasoning_content', None) or getattr(msg, 'reasoning', None) or '')

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        response_format: Optional[Any] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs,
    ) -> Dict[str, Optional[str]]:
        payload = {
            "model": self._resolve_model(model),
            "messages": [msg.to_dict() for msg in messages],
            "stream": False,
            "timeout": timeout,
            **kwargs,
        }
        response_format_payload = self._build_response_format_payload(response_format)
        if response_format_payload:
            payload["response_format"] = response_format_payload
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload = self._sanitize_chat_payload(payload, base_url=self._base_url)

        completion = await self._client.chat.completions.create(**payload)
        if not completion.choices:
            return {"content": "", "finish_reason": None}
        choice = completion.choices[0]
        content = self._coerce_content(getattr(getattr(choice, "message", None), "content", ""))
        return {
            "content": content,
            "finish_reason": getattr(choice, "finish_reason", None),
        }
