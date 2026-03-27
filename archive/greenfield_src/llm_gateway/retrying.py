"""Simple retry wrapper (Stage 7 — no network in default tests)."""

from __future__ import annotations

from src.llm_gateway.types import LlmGateway, LlmRequest


class RetryingGateway:
    def __init__(self, inner: LlmGateway, *, max_retries: int = 2) -> None:
        self._inner = inner
        self._max_retries = max(0, int(max_retries))

    def complete(self, request: LlmRequest) -> str:
        last: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._inner.complete(request)
            except Exception as e:
                last = e
        assert last is not None
        raise last
