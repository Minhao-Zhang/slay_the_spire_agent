from __future__ import annotations

from dataclasses import dataclass

from src.agent.config import AgentConfig
from src.agent.session_state import TurnConversation
from src.agent.v2.protocols import LlmProvider
from src.agent.v2.provider_models import ProviderCapabilities, ProviderDescriptor


@dataclass(frozen=True)
class DecisionRuntimeDeps:
    config: AgentConfig
    system_prompt: str
    session: TurnConversation
    provider_descriptor: ProviderDescriptor
    provider_capabilities: ProviderCapabilities | None
    llm: LlmProvider | None
