from __future__ import annotations

from typing import Any

from src.agent.config import AgentConfig
from src.agent.llm_client import LLMClient
from src.agent.v2.protocols import CapabilityState, LlmProvider, LlmTurnResult, ToolCallback, TraceCallback
from src.agent.v2.provider_models import ProviderCapabilities, ProviderFeatureFlags


class LegacyOpenAILlmProvider(LlmProvider):
    """Adapter that keeps the current OpenAI-compatible client behind the v2 provider protocol."""

    provider_name = "openai_compatible"

    def __init__(self, config: AgentConfig, client: LLMClient | None = None):
        self._config = config
        self._client = client or LLMClient(config)

    @property
    def available(self) -> bool:
        return self._client.available

    @property
    def api_style(self) -> str | None:
        return self._client.api_style

    @property
    def disabled_reason(self) -> str:
        return self._client.disabled_reason

    @property
    def capability_state(self) -> CapabilityState:
        return self._client.capability_state

    def check_api_capabilities(self) -> None:
        self._client.check_api_capabilities()

    def run_streaming_turn(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
        on_delta: TraceCallback | None = None,
        on_tool: ToolCallback | None = None,
    ) -> LlmTurnResult:
        return self._client.run_streaming_turn(
            system_prompt=system_prompt,
            input_items=input_items,
            previous_response_id=previous_response_id,
            on_delta=on_delta,
            on_tool=on_tool,
        )

    def summarize_history_compaction(self, messages: list[dict[str, Any]]) -> str:
        return self._client.summarize_history_compaction(messages)

    def capabilities(self) -> ProviderCapabilities:
        api_style = self._client.api_style or ""
        return ProviderCapabilities(
            provider_name=self.provider_name,
            api_style=api_style,
            capability_state=self._client.capability_state,
            available=self._client.available,
            disabled_reason=self._client.disabled_reason,
            features=ProviderFeatureFlags(
                supports_streaming=True,
                supports_tool_calling=True,
                supports_history_compaction=True,
                supports_responses_api=api_style == "responses",
                supports_chat_completions_api=api_style == "chat_completions",
            ),
        )
