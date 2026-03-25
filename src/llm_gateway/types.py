"""Typed requests/responses for the LLM gateway boundary (no provider imports)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LlmRequest:
    """Single completion: system + user strings (structured output via prompting)."""

    system: str
    user: str
    model: str | None = None


@runtime_checkable
class LlmGateway(Protocol):
    def complete(self, request: LlmRequest) -> str:
        """Return raw model text (expected JSON for tactical proposals)."""
        ...
