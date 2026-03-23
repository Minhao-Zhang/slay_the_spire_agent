from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Literal

import httpx
from openai import OpenAI

from src.agent.config import AgentConfig
from src.agent.schemas import TraceTokenUsage
from src.agent.tool_registry import list_function_tools


TraceCallback = Callable[[str], None]
ToolCallback = Callable[[str], None]
ApiStyle = Literal["responses", "chat_completions"]
CapabilityState = Literal["unchecked", "checking", "ready", "failed"]


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


def _chat_reasoning_from_usage(usage: Any) -> str:
    """Build a fallback reasoning message from Chat Completions usage when no summary is exposed."""
    if not usage:
        return ""
    details = getattr(usage, "completion_tokens_details", None)
    if not details:
        return ""
    n = getattr(details, "reasoning_tokens", None)
    if n is None or not isinstance(n, int) or n <= 0:
        return ""
    return f"(Reasoning used: {n} tokens)"


def _to_chat_tool_schema(response_tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": response_tool.get("name", ""),
            "description": response_tool.get("description", ""),
            "parameters": response_tool.get("parameters", {"type": "object", "properties": {}}),
            "strict": bool(response_tool.get("strict", False)),
        },
    }


def build_llm_check_result(config: AgentConfig) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": False,
        "status": "disabled",
        "api_style": "",
        "message": "",
        "config": {
            "base_url": config.base_url,
            "reasoning_model": config.reasoning_model,
            "fast_model": config.fast_model,
            "prompt_profile": config.prompt_profile,
            "api_key_present": bool(config.api_key),
        },
    }
    if not config.api_key:
        result["message"] = "LLM mis-configured: missing LLM_API_KEY."
        return result
    if not config.reasoning_model:
        result["message"] = "LLM mis-configured: missing LLM_MODEL_REASONING."
        return result

    llm = LLMClient(config)
    llm.check_api_capabilities()
    if llm.available:
        result["enabled"] = True
        result["status"] = "ready"
        result["api_style"] = llm.api_style or ""
        result["message"] = f"LLM connected via {llm.api_style}."
        return result

    result["status"] = "failed" if llm.capability_state == "failed" else "disabled"
    result["message"] = llm.disabled_reason or "LLM is unavailable."
    return result


class LLMClient:
    """API client; use model_key 'reasoning' vs 'fast' for turn routing (see AgentConfig)."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.request_timeout = httpx.Timeout(
            timeout=config.request_timeout_seconds,
            connect=config.connect_timeout_seconds,
        )
        self.probe_timeout = httpx.Timeout(
            timeout=config.probe_timeout_seconds,
            connect=min(config.connect_timeout_seconds, config.probe_timeout_seconds),
        )
        self.client = OpenAI(
            api_key=config.api_key or "missing-key",
            base_url=config.base_url,
            timeout=self.request_timeout,
            max_retries=config.max_retries,
        )
        self.probe_client = OpenAI(
            api_key=config.api_key or "missing-key",
            base_url=config.base_url,
            timeout=self.probe_timeout,
            max_retries=0,
        )
        self.tools = list_function_tools()
        self.chat_tools = [_to_chat_tool_schema(tool) for tool in self.tools]
        self.api_style: ApiStyle | None = None
        self.available = False
        self.disabled_reason = ""
        self.capability_state: CapabilityState = "unchecked"
        self._chat_history: list[dict[str, Any]] = []
        self._capability_lock = threading.Lock()

    def model_name_for_key(self, model_key: str) -> str:
        key = (model_key or "reasoning").strip().lower()
        return self.config.fast_model if key == "fast" else self.config.reasoning_model

    def reasoning_effort_for_key(self, model_key: str) -> str:
        key = (model_key or "reasoning").strip().lower()
        if key == "fast":
            return (self.config.fast_reasoning_effort or "none").strip().lower()
        return (self.config.reasoning_effort or "medium").strip().lower()

    def check_api_capabilities(self) -> None:
        if self.capability_state in {"ready", "failed"}:
            return
        with self._capability_lock:
            if self.capability_state in {"ready", "failed"}:
                return

            self.capability_state = "checking"
            self.available = False
            self.api_style = None
            self.disabled_reason = ""

            if not self.config.api_key:
                self.capability_state = "failed"
                self.disabled_reason = "LLM mis-configured: missing LLM_API_KEY."
                return
            if not self.config.reasoning_model:
                self.capability_state = "failed"
                self.disabled_reason = "LLM mis-configured: missing LLM_MODEL_REASONING."
                return

            responses_error = self._probe_responses_api()
            if responses_error and self._should_retry_probe(responses_error):
                responses_error = self._verify_responses_api()
            if not responses_error:
                self.api_style = "responses"
                self.available = True
                self.capability_state = "ready"
                return

            chat_error = self._probe_chat_completions_api()
            if chat_error and self._should_retry_probe(chat_error):
                chat_error = self._verify_chat_completions_api()
            if not chat_error:
                self.api_style = "chat_completions"
                self.available = True
                self.capability_state = "ready"
                return

            self.capability_state = "failed"
            self.disabled_reason = (
                "LLM mis-configured: both Responses API and Chat Completions API checks failed. "
                f"responses={responses_error}; chat_completions={chat_error}"
            )

    @staticmethod
    def _summarize_exception(exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        message = str(exc).strip() or exc.__class__.__name__
        if isinstance(status_code, int):
            return f"HTTP {status_code}: {message}"
        return message

    @staticmethod
    def _should_retry_probe(error: str) -> bool:
        lowered = error.lower()
        return "timed out" in lowered or "timeout" in lowered

    def _probe_responses_api(self) -> str | None:
        try:
            self._basic_responses_text(self.probe_client, "ping")
            return None
        except Exception as exc:  # noqa: BLE001
            return self._summarize_exception(exc)

    def _probe_chat_completions_api(self) -> str | None:
        try:
            self._basic_chat_text(self.probe_client, "ping")
            return None
        except Exception as exc:  # noqa: BLE001
            return self._summarize_exception(exc)

    def _verify_responses_api(self) -> str | None:
        try:
            self._basic_responses_text(self.client, "ping")
            return None
        except Exception as exc:  # noqa: BLE001
            return self._summarize_exception(exc)

    def _verify_chat_completions_api(self) -> str | None:
        try:
            self._basic_chat_text(self.client, "ping")
            return None
        except Exception as exc:  # noqa: BLE001
            return self._summarize_exception(exc)

    def _basic_chat_text(self, client: OpenAI, message: str) -> str:
        completion = client.chat.completions.create(
            model=self.config.reasoning_model,
            messages=[{"role": "user", "content": message}],
        )
        choices = getattr(completion, "choices", None) or []
        if not choices:
            return ""
        choice_message = getattr(choices[0], "message", None)
        return (getattr(choice_message, "content", None) or "").strip()

    def _basic_responses_text(self, client: OpenAI, message: str) -> str:
        response = client.responses.create(
            model=self.config.reasoning_model,
            reasoning={"effort": self.config.reasoning_effort},
            input=[{"role": "user", "content": message}],
        )
        return (getattr(response, "output_text", None) or "").strip()

    def run_basic_text_check(self, message: str = "hello") -> str:
        self.check_api_capabilities()
        if not self.available or not self.api_style:
            raise RuntimeError(self.disabled_reason or "LLM is unavailable for this run.")

        return self.run_basic_text_check_with_style(self.api_style, message)

    def run_basic_text_check_with_style(self, api_style: ApiStyle, message: str = "hello") -> str:
        if api_style == "chat_completions":
            return self._basic_chat_text(self.client, message)

        return self._basic_responses_text(self.client, message)

    def _stream_response(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
        model_name: str | None = None,
        model_key: str = "reasoning",
    ):
        model = model_name or self.model_name_for_key(model_key)
        effort = self.reasoning_effort_for_key(model_key)
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": system_prompt,
            "tools": self.tools,
            "input": input_items,
            "previous_response_id": previous_response_id,
        }
        if effort and effort != "none":
            kwargs["reasoning"] = {"summary": "auto", "effort": effort}
        return self.client.responses.stream(**kwargs)

    def _to_chat_messages(self, system_prompt: str, input_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        has_role_messages = any("role" in item for item in input_items)
        if has_role_messages:
            messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            for item in input_items:
                role = item.get("role")
                content = item.get("content", "")
                if role in {"user", "assistant"}:
                    messages.append({"role": role, "content": content})
            self._chat_history = messages
            return self._chat_history

        # Tool continuation for the active in-memory thread.
        for item in input_items:
            if item.get("type") != "function_call_output":
                continue
            self._chat_history.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": item.get("output", ""),
                }
            )
        return self._chat_history

    def _run_streaming_turn_responses(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
        on_delta: TraceCallback | None = None,
        on_tool: ToolCallback | None = None,
        model_key: str = "reasoning",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        raw_chunks: list[str] = []

        with self._stream_response(
            system_prompt=system_prompt,
            input_items=input_items,
            previous_response_id=previous_response_id,
            model_key=model_key,
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

    def _run_streaming_turn_chat_completions(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        on_delta: TraceCallback | None = None,
        on_tool: ToolCallback | None = None,
        model_key: str = "reasoning",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        raw_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        response_id = ""
        usage = TraceTokenUsage()
        last_chunk_usage: Any = None
        tool_deltas: dict[int, dict[str, Any]] = {}

        messages = self._to_chat_messages(system_prompt, input_items)
        model_name = self.model_name_for_key(model_key)
        effort = self.reasoning_effort_for_key(model_key)
        create_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "tools": self.chat_tools,
            "stream": True,
            "tool_choice": "auto",
        }
        if effort and effort != "none":
            create_kwargs["reasoning_effort"] = effort
        try:
            stream = self.client.chat.completions.create(**create_kwargs)
        except TypeError:
            create_kwargs.pop("reasoning_effort", None)
            stream = self.client.chat.completions.create(**create_kwargs)

        for chunk in stream:
            if not response_id:
                response_id = getattr(chunk, "id", "") or ""

            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage:
                last_chunk_usage = chunk_usage
                usage = TraceTokenUsage(
                    input_tokens=getattr(chunk_usage, "prompt_tokens", None),
                    output_tokens=getattr(chunk_usage, "completion_tokens", None),
                    total_tokens=getattr(chunk_usage, "total_tokens", None),
                )

            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if not delta:
                continue

            content_parts = getattr(delta, "content_parts", None)
            if content_parts is not None and isinstance(content_parts, list):
                for part in content_parts:
                    part_type = (getattr(part, "type", None) or "").lower()
                    text = (getattr(part, "text", None) or getattr(part, "content", None) or "").strip()
                    if not text:
                        continue
                    if part_type in ("thinking", "reasoning"):
                        reasoning_chunks.append(text)
                    else:
                        raw_chunks.append(text)
                        if on_delta:
                            on_delta(text)
            else:
                content_delta = getattr(delta, "content", None) or ""
                if content_delta:
                    raw_chunks.append(content_delta)
                    if on_delta:
                        on_delta(content_delta)

            for tool_call in getattr(delta, "tool_calls", None) or []:
                index = getattr(tool_call, "index", 0)
                entry = tool_deltas.setdefault(
                    index,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                tool_id = getattr(tool_call, "id", None)
                if tool_id:
                    entry["id"] = tool_id

                function_data = getattr(tool_call, "function", None)
                if function_data:
                    function_name = getattr(function_data, "name", None)
                    function_arguments = getattr(function_data, "arguments", None)
                    if function_name:
                        entry["function"]["name"] = function_name
                        if on_tool:
                            on_tool(function_name)
                    if function_arguments:
                        entry["function"]["arguments"] += function_arguments

        output_text = "".join(raw_chunks)
        sorted_tool_calls = [tool_deltas[idx] for idx in sorted(tool_deltas)]
        tool_events: list[dict[str, Any]] = []
        for tool_call in sorted_tool_calls:
            function_data = tool_call.get("function") or {}
            arguments = function_data.get("arguments", "") or ""
            tool_events.append(
                {
                    "id": tool_call.get("id", ""),
                    "call_id": tool_call.get("id", ""),
                    "name": function_data.get("name", ""),
                    "arguments": arguments,
                    "parsed_arguments": _parse_tool_arguments(arguments),
                }
            )

        if output_text or tool_events:
            assistant_message: dict[str, Any] = {"role": "assistant", "content": output_text}
            if sorted_tool_calls:
                assistant_message["tool_calls"] = sorted_tool_calls
            self._chat_history.append(assistant_message)

        reasoning_summary_text = "\n\n".join(reasoning_chunks).strip()
        if not reasoning_summary_text and last_chunk_usage:
            reasoning_summary_text = _chat_reasoning_from_usage(last_chunk_usage)

        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "response_id": response_id,
            "raw_output": output_text,
            "assistant_content": output_text,
            "tool_calls": tool_events,
            "reasoning_summary_text": reasoning_summary_text,
            "latency_ms": latency_ms,
            "token_usage": usage,
        }

    def summarize_history_compaction(self, messages: list[dict[str, Any]]) -> str:
        """Summarize older conversation turns before compacting them into memory."""
        if not messages:
            return ""
        if not self.available or not self.client:
            return ""
        try:
            transcript = "\n\n".join(
                f"{m.get('role', '?')}: {m.get('content', '')[:500]}"
                for m in messages
                if m.get("role") in ("user", "assistant") and m.get("content")
            )
            if not transcript.strip():
                return ""
            prompt = (
                "Summarize these older Slay the Spire agent turns into a compact memory block. "
                "Keep it to 4 short bullet points maximum. Focus on persistent strategy context: deck direction, "
                "important relics or scaling pieces, pathing goals, boss preparation, and unusual constraints. "
                "Do not restate routine board-state details that will appear in the live prompt."
            )
            # Optional reasoning effort for the fast model summarization.
            # If set to "none", we omit the SDK parameter entirely for compatibility.
            fast_effort = (self.config.fast_reasoning_effort or "").strip().lower()
            if fast_effort and fast_effort != "none":
                try:
                    completion = self.client.chat.completions.create(
                        model=self.config.fast_model,
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": transcript},
                        ],
                        reasoning_effort=fast_effort,
                    )
                except TypeError:
                    completion = self.client.chat.completions.create(
                        model=self.config.fast_model,
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": transcript},
                        ],
                    )
            else:
                completion = self.client.chat.completions.create(
                    model=self.config.fast_model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": transcript},
                    ],
                )
            choices = getattr(completion, "choices", None) or []
            if not choices:
                return ""
            content = getattr(choices[0].message, "content", None) or ""
            return content.strip()
        except Exception:  # noqa: BLE001
            return ""

    def run_streaming_turn(
        self,
        *,
        system_prompt: str,
        input_items: list[dict[str, Any]],
        previous_response_id: str | None = None,
        on_delta: TraceCallback | None = None,
        on_tool: ToolCallback | None = None,
        model_key: str = "reasoning",
    ) -> dict:
        self.check_api_capabilities()
        if self.capability_state == "checking":
            raise RuntimeError("LLM configuration check is still running.")
        if not self.available or not self.api_style:
            raise RuntimeError(self.disabled_reason or "LLM is unavailable for this run.")
        if self.api_style == "chat_completions":
            return self._run_streaming_turn_chat_completions(
                system_prompt=system_prompt,
                input_items=input_items,
                on_delta=on_delta,
                on_tool=on_tool,
                model_key=model_key,
            )
        return self._run_streaming_turn_responses(
            system_prompt=system_prompt,
            input_items=input_items,
            previous_response_id=previous_response_id,
            on_delta=on_delta,
            on_tool=on_tool,
            model_key=model_key,
        )

    def generate_combat_plan(
        self,
        *,
        system_prompt: str,
        user_content: str,
        max_output_tokens: int | None = None,
        model_key: str = "reasoning",
    ) -> dict[str, Any]:
        """Single non-streaming completion without tools (opening combat battle guide)."""
        self.check_api_capabilities()
        if self.capability_state == "checking":
            raise RuntimeError("LLM configuration check is still running.")
        if not self.available or not self.api_style:
            raise RuntimeError(self.disabled_reason or "LLM is unavailable for this run.")
        cap = (
            max_output_tokens
            if max_output_tokens is not None
            else self.config.combat_plan_max_output_tokens
        )
        model_name = self.model_name_for_key(model_key)
        effort = self.reasoning_effort_for_key(model_key)
        started = time.perf_counter()
        if self.api_style == "chat_completions":
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            }
            if effort and effort != "none":
                kwargs["reasoning_effort"] = effort
            try:
                completion = self.client.chat.completions.create(**kwargs, max_completion_tokens=cap)
            except TypeError:
                kwargs.pop("reasoning_effort", None)
                try:
                    completion = self.client.chat.completions.create(**kwargs, max_completion_tokens=cap)
                except TypeError:
                    completion = self.client.chat.completions.create(**kwargs)
            choices = getattr(completion, "choices", None) or []
            text = ""
            if choices:
                text = (getattr(choices[0].message, "content", None) or "").strip()
            usage_data = getattr(completion, "usage", None)
            usage = TraceTokenUsage(
                input_tokens=getattr(usage_data, "prompt_tokens", None) if usage_data else None,
                output_tokens=getattr(usage_data, "completion_tokens", None) if usage_data else None,
                total_tokens=getattr(usage_data, "total_tokens", None) if usage_data else None,
            )
        else:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "instructions": system_prompt,
                "input": [{"role": "user", "content": user_content}],
            }
            if effort and effort != "none":
                kwargs["reasoning"] = {"effort": effort}
            try:
                response = self.client.responses.create(**kwargs, max_output_tokens=cap)
            except TypeError:
                response = self.client.responses.create(**kwargs)
            text = (getattr(response, "output_text", None) or "").strip()
            usage_data = getattr(response, "usage", None)
            usage = TraceTokenUsage(
                input_tokens=getattr(usage_data, "input_tokens", None) if usage_data else None,
                output_tokens=getattr(usage_data, "output_tokens", None) if usage_data else None,
                total_tokens=getattr(usage_data, "total_tokens", None) if usage_data else None,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "raw_output": text,
            "token_usage": usage,
            "latency_ms": latency_ms,
        }

