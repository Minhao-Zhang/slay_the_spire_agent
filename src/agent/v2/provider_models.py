from __future__ import annotations

from pydantic import BaseModel, Field

from src.agent.v2.protocols import CapabilityState


class ProviderFeatureFlags(BaseModel):
    supports_streaming: bool = True
    supports_tool_calling: bool = True
    supports_history_compaction: bool = True
    supports_responses_api: bool = False
    supports_chat_completions_api: bool = False


class ProviderDescriptor(BaseModel):
    provider_name: str
    base_url: str
    reasoning_model: str
    fast_model: str = ""
    api_key_present: bool = False
    transport: str = "openai-compatible"


class ProviderCapabilities(BaseModel):
    provider_name: str
    api_style: str = ""
    capability_state: CapabilityState = "unchecked"
    available: bool = False
    disabled_reason: str = ""
    features: ProviderFeatureFlags = Field(default_factory=ProviderFeatureFlags)
