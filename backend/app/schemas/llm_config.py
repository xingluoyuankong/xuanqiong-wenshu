from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class LLMProfileItem(BaseModel):
    value: str = Field(..., description="Profile item value, such as API key or model name")
    enabled: bool = Field(default=True, description="Whether the item is enabled")
    retain_existing: bool = Field(default=False, description="Keep the stored secret when the client does not resend it")


class LLMProfileItemRead(BaseModel):
    value: str = Field(default="", description="User-entered value. Secrets are not echoed back here")
    enabled: bool = Field(default=True, description="Whether the item is enabled")
    masked_value: Optional[str] = Field(default=None, description="Masked secret preview")
    has_value: bool = Field(default=False, description="Whether a stored value exists")
    is_masked: bool = Field(default=False, description="Whether the returned item is a masked secret placeholder")


class LLMProviderProfile(BaseModel):
    id: Optional[str] = Field(default=None, description="Profile unique id")
    name: Optional[str] = Field(default=None, description="Profile display name")
    enabled: bool = Field(default=True, description="Whether this provider profile is enabled")
    llm_provider_url: Optional[str] = Field(default=None, description="Provider base URL")
    api_keys: List[LLMProfileItem] = Field(default_factory=list, description="API key list")
    models: List[LLMProfileItem] = Field(default_factory=list, description="Model list")


class LLMProviderProfileRead(BaseModel):
    id: Optional[str] = Field(default=None, description="Profile unique id")
    name: Optional[str] = Field(default=None, description="Profile display name")
    enabled: bool = Field(default=True, description="Whether this provider profile is enabled")
    llm_provider_url: Optional[str] = Field(default=None, description="Provider base URL")
    api_keys: List[LLMProfileItemRead] = Field(default_factory=list, description="Masked API key list")
    models: List[LLMProfileItem] = Field(default_factory=list, description="Model list")


class LLMConfigBase(BaseModel):
    llm_provider_url: Optional[str] = Field(default=None, description="Custom provider URL")
    llm_provider_api_key: Optional[str] = Field(default=None, description="Custom provider API key")
    llm_provider_model: Optional[str] = Field(default=None, description="Custom provider model")
    llm_provider_profiles: Optional[List[LLMProviderProfile]] = Field(
        default=None,
        description="Multi-profile provider configuration",
    )


class LLMConfigCreate(LLMConfigBase):
    pass


class LLMConfigRead(BaseModel):
    user_id: int
    llm_provider_url: Optional[str] = Field(default=None, description="Custom provider URL")
    llm_provider_model: Optional[str] = Field(default=None, description="Custom provider model")
    llm_provider_api_key_masked: Optional[str] = Field(default=None, description="Masked primary API key")
    llm_provider_api_key_configured: bool = Field(default=False, description="Whether a primary API key is stored")
    llm_provider_profiles: List[LLMProviderProfileRead] = Field(default_factory=list, description="Masked multi-profile provider configuration")

    model_config = ConfigDict(from_attributes=True)


class ModelListRequest(BaseModel):
    llm_provider_url: Optional[str] = Field(default=None, description="Provider base URL")
    llm_provider_api_key: str = Field(..., description="Provider API key")


class LLMProviderKeyHealth(BaseModel):
    key_index: int = Field(..., description="Key index (1-based)")
    key_mask: str = Field(..., description="Masked key")
    enabled: bool = Field(default=True, description="Whether the key is enabled")
    reachable: bool = Field(default=False, description="Network reachability")
    usable: bool = Field(default=False, description="Whether requests can succeed")
    model_count: int = Field(default=0, description="Detected model count")
    status_code: Optional[int] = Field(default=None, description="HTTP status from probe")
    latency_ms: Optional[int] = Field(default=None, description="Probe latency in ms")
    detail: Optional[str] = Field(default=None, description="Diagnostic detail")


class LLMProviderHealth(BaseModel):
    profile_id: str = Field(..., description="Profile id")
    profile_name: str = Field(..., description="Profile name")
    enabled: bool = Field(default=True, description="Whether profile is enabled")
    llm_provider_url: Optional[str] = Field(default=None, description="Profile URL")
    status: str = Field(..., description="healthy/degraded/down/no_key")
    summary: str = Field(..., description="Human-readable status summary")
    reachable: bool = Field(default=False, description="Profile-level reachability")
    usable: bool = Field(default=False, description="Profile-level usability")
    model_count: int = Field(default=0, description="Available model count")
    checked_key_count: int = Field(default=0, description="Checked key count")
    keys: List[LLMProviderKeyHealth] = Field(default_factory=list, description="Per-key health details")


class LLMHealthCheckResponse(BaseModel):
    checked_at: datetime = Field(..., description="Check timestamp")
    overall_status: str = Field(..., description="ok/degraded/down")
    has_usable_profile: bool = Field(default=False, description="Whether any profile is usable")
    recommended_profile_id: Optional[str] = Field(default=None, description="Recommended target profile id")
    recommended_profile_name: Optional[str] = Field(default=None, description="Recommended target profile name")
    current_profile_id: Optional[str] = Field(default=None, description="Current active profile id")
    current_profile_name: Optional[str] = Field(default=None, description="Current active profile name")
    current_profile_usable: Optional[bool] = Field(default=None, description="Whether current active profile is usable")
    recommended_action: Optional[str] = Field(default=None, description="Recommended next action text")
    profiles: List[LLMProviderHealth] = Field(default_factory=list, description="All profile health results")


class LLMAutoSwitchResponse(BaseModel):
    switched: bool = Field(default=False, description="Whether auto switch happened")
    reason: str = Field(..., description="Switch outcome summary")
    switch_basis: Optional[str] = Field(default=None, description="Switch decision basis")
    previous_profile_id: Optional[str] = Field(default=None, description="Profile id before switching")
    previous_profile_name: Optional[str] = Field(default=None, description="Profile name before switching")
    active_profile_id: Optional[str] = Field(default=None, description="Profile id after switching")
    active_profile_name: Optional[str] = Field(default=None, description="Profile name after switching")
    health: LLMHealthCheckResponse = Field(..., description="Health snapshot used for switch")
    config: Optional[LLMConfigRead] = Field(default=None, description="Updated config after switch")
