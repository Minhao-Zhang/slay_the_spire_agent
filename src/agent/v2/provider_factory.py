from __future__ import annotations

import os

from src.agent.config import AgentConfig
from src.agent.v2.adapters.legacy_openai import LegacyOpenAILlmProvider
from src.agent.v2.protocols import LlmProvider
from src.agent.v2.provider_models import ProviderDescriptor

DEFAULT_PROVIDER_NAME = "openai_compatible"


def build_provider_descriptor(config: AgentConfig) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider_name=DEFAULT_PROVIDER_NAME,
        base_url=config.base_url,
        reasoning_model=config.reasoning_model,
        fast_model=config.fast_model,
        api_key_present=bool(config.api_key),
    )


def build_llm_provider(config: AgentConfig) -> LlmProvider:
    provider_name = os.getenv("SPIRE_LLM_PROVIDER", DEFAULT_PROVIDER_NAME).strip().lower()
    if provider_name not in {DEFAULT_PROVIDER_NAME, "legacy_openai"}:
        raise ValueError(
            "Unsupported SPIRE_LLM_PROVIDER. "
            f"Expected one of: {DEFAULT_PROVIDER_NAME}, legacy_openai. "
            f"Got: {provider_name!r}"
        )
    return LegacyOpenAILlmProvider(config)
