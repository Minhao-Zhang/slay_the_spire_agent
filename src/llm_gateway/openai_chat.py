"""OpenAI-backed gateway (optional; requires ``OPENAI_API_KEY`` in the environment)."""

from __future__ import annotations

import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.llm_gateway.types import LlmGateway, LlmRequest


class OpenAiChatGateway:
    def __init__(
        self,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        mid = model or os.environ.get("SLAY_OPENAI_MODEL", "gpt-5.4")
        self._chat = ChatOpenAI(model=mid, temperature=temperature, max_retries=2)

    def complete(self, request: LlmRequest) -> str:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set; use SLAY_LLM_BACKEND=stub for offline runs",
            )
        msg = self._chat.invoke(
            [
                SystemMessage(content=request.system),
                HumanMessage(content=request.user),
            ],
        )
        return str(msg.content)
