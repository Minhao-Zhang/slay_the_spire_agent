"""Deterministic gateway for CI and offline runs."""

from __future__ import annotations

from src.llm_gateway.types import LlmGateway, LlmRequest


class StubLlmGateway:
    """Returns a fixed string or a cheap default JSON payload."""

    def __init__(self, *, fixed_response: str | None = None) -> None:
        self._fixed = fixed_response

    def complete(self, request: LlmRequest) -> str:
        _ = request
        if self._fixed is not None:
            return self._fixed
        return '{"command": null, "rationale": "stub_llm_gateway_default"}'
