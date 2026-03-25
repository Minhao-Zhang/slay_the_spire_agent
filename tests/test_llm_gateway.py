from __future__ import annotations

import pytest

from src.llm_gateway.retrying import RetryingGateway
from src.llm_gateway.stub import StubLlmGateway
from src.llm_gateway.types import LlmRequest


def test_stub_default_returns_json_string() -> None:
    g = StubLlmGateway()
    out = g.complete(LlmRequest(system="s", user="u"))
    assert "command" in out


def test_stub_fixed_response() -> None:
    g = StubLlmGateway(fixed_response='{"command": "END"}')
    assert g.complete(LlmRequest(system="", user="")) == '{"command": "END"}'


def test_retrying_gateway_succeeds_after_failures() -> None:
    class Flaky:
        def __init__(self) -> None:
            self.n = 0

        def complete(self, request: LlmRequest) -> str:
            self.n += 1
            if self.n < 3:
                raise ConnectionError("nope")
            return "ok"

    rg = RetryingGateway(Flaky(), max_retries=3)
    assert rg.complete(LlmRequest("", "")) == "ok"


def test_retrying_gateway_exhausts() -> None:
    class Always:
        def complete(self, request: LlmRequest) -> str:
            raise RuntimeError("x")

    rg = RetryingGateway(Always(), max_retries=2)
    with pytest.raises(RuntimeError):
        rg.complete(LlmRequest("", ""))
