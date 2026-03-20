from __future__ import annotations

from src.agent.config import get_agent_config, load_system_prompt
from src.agent.graph import SpireDecisionAgent
from src.agent.session_state import TurnConversation
from src.agent.v2.deps import DecisionRuntimeDeps
from src.agent.v2.graph_builder import build_spire_decision_graph
from src.agent.v2.provider_factory import build_llm_provider, build_provider_descriptor
from src.agent.v2.provider_models import ProviderCapabilities
from src.agent.v2.protocols import LlmProvider


class V2SpireDecisionAgent(SpireDecisionAgent):
    """Compatibility-first v2 runtime with provider injection and external graph builder."""

    def __init__(self, llm_provider: LlmProvider | None = None):
        self.config = get_agent_config()
        self.system_prompt = load_system_prompt()
        self.session = TurnConversation()
        self.provider_descriptor = build_provider_descriptor(self.config)
        self.llm = llm_provider or (build_llm_provider(self.config) if self.config.enabled else None)
        self.ai_enabled = False
        self.ai_status = "disabled"
        self.ai_api_style = ""
        if not self.config.api_key:
            self.ai_disabled_reason = "LLM mis-configured: missing LLM_API_KEY."
            self.ai_status = "disabled"
        elif not self.config.reasoning_model:
            self.ai_disabled_reason = "LLM mis-configured: missing LLM_MODEL_REASONING."
            self.ai_status = "disabled"
        elif self.llm:
            self.ai_disabled_reason = "Checking LLM configuration..."
            self.ai_status = "checking"
        else:
            self.ai_disabled_reason = "LLM is not configured."
            self.ai_status = "disabled"
        self.trace_callback = None
        self.provider_capabilities = self._provider_capabilities_snapshot()
        self._deps = DecisionRuntimeDeps(
            config=self.config,
            system_prompt=self.system_prompt,
            session=self.session,
            provider_descriptor=self.provider_descriptor,
            provider_capabilities=self.provider_capabilities,
            llm=self.llm,
        )
        self.graph = build_spire_decision_graph(self)

    def _provider_capabilities_snapshot(self) -> ProviderCapabilities | None:
        if not self.llm:
            return None
        return self.llm.capabilities()

    def initialize_ai_runtime(self) -> dict[str, str | bool | dict]:
        result = super().initialize_ai_runtime()
        self.provider_capabilities = self._provider_capabilities_snapshot()
        self._deps = DecisionRuntimeDeps(
            config=self.config,
            system_prompt=self.system_prompt,
            session=self.session,
            provider_descriptor=self.provider_descriptor,
            provider_capabilities=self.provider_capabilities,
            llm=self.llm,
        )
        result["provider_name"] = self.provider_descriptor.provider_name
        if self.provider_capabilities:
            result["provider_capabilities"] = self.provider_capabilities.model_dump(mode="json")
        return result


__all__ = ["V2SpireDecisionAgent"]
