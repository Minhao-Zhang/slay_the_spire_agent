"""
Dispatch tactical command selection: deterministic mock vs LLM + agent_core.

Configurable via ``RunnableConfig.configurable["proposer"]`` (``mock`` | ``llm``)
or env ``SLAY_PROPOSER`` (default ``mock``). LLM backend: ``SLAY_LLM_BACKEND``
``stub`` (default) or ``openai`` (needs ``OPENAI_API_KEY``).
Tests can call ``set_llm_gateway_for_tests(...)``.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.agent_core.pipeline import propose_from_gateway
from src.decision_engine.proposal_logic import mock_propose_command
from src.llm_gateway.openai_chat import OpenAiChatGateway
from src.llm_gateway.stub import StubLlmGateway
from src.llm_gateway.types import LlmGateway

_llm_override: LlmGateway | None = None


def set_llm_gateway_for_tests(gateway: LlmGateway | None) -> None:
    global _llm_override
    _llm_override = gateway


def _default_llm_gateway() -> LlmGateway:
    backend = os.environ.get("SLAY_LLM_BACKEND", "stub").strip().lower()
    if backend == "openai":
        return OpenAiChatGateway()
    return StubLlmGateway()


def get_llm_gateway() -> LlmGateway:
    if _llm_override is not None:
        return _llm_override
    return _default_llm_gateway()


def propose_for_view_model(
    view_model: dict[str, Any] | None,
    config: RunnableConfig,
) -> tuple[str | None, str, str | None, dict[str, Any] | None]:
    """
    (command, resolve_or_error_tag, raw_llm_text_or_none, parsed_model_or_none).

    Mock path has no raw text; ``parsed_model`` echoes command + tag for UI parity.
    """
    conf = config.get("configurable") or {}
    proposer = conf.get("proposer")
    if proposer is None:
        proposer = os.environ.get("SLAY_PROPOSER", "mock").strip().lower()
    else:
        proposer = str(proposer).strip().lower()
    if proposer == "llm":
        return propose_from_gateway(view_model, get_llm_gateway())
    cmd, tag = mock_propose_command(view_model)
    parsed = (
        {"command": cmd, "rationale": tag, "source": "mock"}
        if cmd
        else None
    )
    return cmd, tag, None, parsed
