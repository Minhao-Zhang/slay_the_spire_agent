from __future__ import annotations

import json
import time
from typing import Any, Callable

from openai import OpenAI

from src.agent.config import AgentConfig
from src.agent.schemas import (
    InspectDiscardPileTool,
    InspectDrawPileTool,
    InspectExhaustPileTool,
    TraceTokenUsage,
)


TraceCallback = Callable[[str], None]
ToolCallback = Callable[[str], None]


def _build_function_tool(schema_model: type) -> dict[str, Any]:
    return {
        "type": "function",
        "name": schema_model.__name__,
        "description": (
            (schema_model.__doc__ or "").strip()
            or f"Inspect the corresponding pile and answer a focused question about it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Why you want to inspect this pile or what you are checking for.",
                }
            },
            "required": ["question"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_reasoning_summary(response: Any) -> str:
    summaries: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", "") != "reasoning":
            continue
        for summary_item in getattr(item, "summary", []) or []:
            text = getattr(summary_item, "text", "") or ""
            if text.strip():
                summaries.append(text.strip())
    return "\n\n".join(summaries).strip()


class LLMClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key or "missing-key",
            base_url=config.base_url,
        )
        self.tools = [
            _build_function_tool(InspectDrawPileTool),
            _build_function_tool(InspectDiscardPileTool),
            _build_function_tool(InspectExhaustPileTool),
        ]

    def _stream_response(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
    ):
        return self.client.responses.stream(
            model=self.config.reasoning_model,
            instructions=system_prompt,
            tools=self.tools,
            input=input_items,
            previous_response_id=previous_response_id,
            reasoning={"summary": "auto"},
        )

    def run_streaming_turn(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
        on_delta: TraceCallback | None = None,
        on_tool: ToolCallback | None = None,
    ) -> dict:
        started = time.perf_counter()
        raw_chunks: list[str] = []

        with self._stream_response(
            system_prompt=system_prompt,
            input_items=input_items,
            previous_response_id=previous_response_id,
        ) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if not delta:
                        continue
                    raw_chunks.append(delta)
                    if on_delta:
                        on_delta(delta)
                elif event.type == "response.function_call_arguments.done":
                    tool_name = getattr(event, "name", "")
                    if on_tool and tool_name:
                        on_tool(tool_name)
            response = stream.get_final_response()

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage_data = getattr(response, "usage", None)
        usage = TraceTokenUsage(
            input_tokens=getattr(usage_data, "input_tokens", None) if usage_data else None,
            output_tokens=getattr(usage_data, "output_tokens", None) if usage_data else None,
            total_tokens=getattr(usage_data, "total_tokens", None) if usage_data else None,
        )

        tool_events: list[dict[str, Any]] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", "") != "function_call":
                continue
            arguments = getattr(item, "arguments", "") or ""
            tool_events.append(
                {
                    "id": getattr(item, "id", "") or getattr(item, "call_id", ""),
                    "call_id": getattr(item, "call_id", ""),
                    "name": getattr(item, "name", ""),
                    "arguments": arguments,
                    "parsed_arguments": _parse_tool_arguments(arguments),
                }
            )

        output_text = getattr(response, "output_text", "") or ""
        return {
            "response_id": getattr(response, "id", ""),
            "raw_output": "".join(raw_chunks) or output_text,
            "assistant_content": output_text,
            "tool_calls": tool_events,
            "reasoning_summary_text": _extract_reasoning_summary(response),
            "latency_ms": latency_ms,
            "token_usage": usage,
        }

