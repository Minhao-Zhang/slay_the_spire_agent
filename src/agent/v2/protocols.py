from __future__ import annotations

from typing import Any, Callable, Literal, Protocol, TypedDict, runtime_checkable


TraceCallback = Callable[[str], None]
ToolCallback = Callable[[str], None]
CapabilityState = Literal["unchecked", "checking", "ready", "failed"]


class LlmTurnResult(TypedDict):
    raw_output: str
    reasoning_summary_text: str
    tool_calls: list[dict[str, Any]]
    response_id: str | None
    latency_ms: int | None
    token_usage: Any


@runtime_checkable
class LlmProvider(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def api_style(self) -> str | None: ...

    @property
    def disabled_reason(self) -> str: ...

    @property
    def capability_state(self) -> CapabilityState: ...

    def check_api_capabilities(self) -> None: ...

    def run_streaming_turn(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
        on_delta: TraceCallback | None = None,
        on_tool: ToolCallback | None = None,
    ) -> LlmTurnResult: ...

    def summarize_history_compaction(self, messages: list[dict[str, Any]]) -> str: ...
