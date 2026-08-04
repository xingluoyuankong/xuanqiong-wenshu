from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


ResearchMode = Literal["auto", "ask", "off"]
ResearchScope = Literal["global", "enhanced", "chapter"]


class ResearchConfigUpdate(BaseModel):
    mode: ResearchMode = "auto"
    enabled: bool = True
    search_provider: Literal["tavily", "serper", "bing", "none"] = "tavily"
    search_base_url: Optional[str] = None
    search_api_key: Optional[str] = None
    clear_search_api_key: bool = False
    research_llm_base_url: Optional[str] = None
    research_llm_model: Optional[str] = None
    research_llm_api_key: Optional[str] = None
    clear_research_llm_api_key: bool = False
    reuse_writing_llm: bool = True
    local_model_enabled: bool = False
    global_research_enabled: bool = True
    enhanced_research_enabled: bool = True
    chapter_research_enabled: bool = True
    max_parallel_queries: int = Field(default=4, ge=1, le=8)
    max_results_per_query: int = Field(default=5, ge=1, le=10)
    preferred_domains: List[str] = Field(default_factory=list)
    blocked_domains: List[str] = Field(default_factory=list)
    category_preferences: List[str] = Field(default_factory=list)

    @field_validator("search_base_url", "research_llm_base_url")
    @classmethod
    def validate_cloud_base_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        normalized = value.strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Base URL 必须是无内嵌凭据的 HTTP(S) 云端地址")
        host = parsed.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith(".localhost"):
            raise ValueError("Base URL 不允许指向本机或私有网络")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError("Base URL 不允许指向本机、私有、链路本地或保留地址")
        return normalized

    @field_validator("local_model_enabled")
    @classmethod
    def reject_local_model_by_default(cls, value: bool) -> bool:
        if value:
            raise ValueError("本地研究模型默认禁用；当前版本不允许通过项目配置隐式启用")
        return False


class ResearchConfigRead(BaseModel):
    project_id: str
    mode: ResearchMode = "auto"
    enabled: bool = True
    search_provider: str = "tavily"
    search_base_url: Optional[str] = None
    search_api_key_masked: Optional[str] = None
    search_api_key_configured: bool = False
    research_llm_base_url: Optional[str] = None
    research_llm_model: Optional[str] = None
    research_llm_api_key_masked: Optional[str] = None
    research_llm_api_key_configured: bool = False
    reuse_writing_llm: bool = True
    local_model_enabled: bool = False
    global_research_enabled: bool = True
    enhanced_research_enabled: bool = True
    chapter_research_enabled: bool = True
    max_parallel_queries: int = 4
    max_results_per_query: int = 5
    preferred_domains: List[str] = Field(default_factory=list)
    blocked_domains: List[str] = Field(default_factory=list)
    category_preferences: List[str] = Field(default_factory=list)
    provider_priority: List[str] = Field(default_factory=lambda: ["search_api_key", "research_llm_api_key", "writing_llm_api_key"])


class ResearchRunRequest(BaseModel):
    scope: ResearchScope
    chapter_number: Optional[int] = Field(default=None, ge=1)
    consent: bool = False
    force: bool = False
    trigger: str = "manual"
    context: Dict[str, Any] = Field(default_factory=dict)


class ResearchJobRead(BaseModel):
    run_id: str
    project_id: str
    scope: str
    chapter_number: Optional[int] = None
    status: str
    cancel_signal_sent: bool = False
    in_process_task_cancelled: bool = False
    artifact: Optional["ResearchArtifactRead"] = None


class ResearchArtifactRead(BaseModel):
    id: int
    run_id: str
    project_id: str
    scope: str
    chapter_number: Optional[int] = None
    status: str
    trigger: str
    query_plan: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    category_payload: Dict[str, Any] = Field(default_factory=dict)
    summary: Optional[str] = None
    file_manifest: Dict[str, Any] = Field(default_factory=dict)
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
