from __future__ import annotations

from dataclasses import dataclass

from src.agent.config import AgentConfig
from src.agent.session_state import TurnConversation
from src.agent.v2.protocols import LlmProvider


@dataclass(frozen=True)
class DecisionRuntimeDeps:
    config: AgentConfig
    system_prompt: str
    session: TurnConversation
    llm: LlmProvider | None
