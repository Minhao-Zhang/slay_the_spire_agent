"""OpenAI-backed gateway (optional; requires ``OPENAI_API_KEY`` in the environment)."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
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
        self._model_id = mid
        self._chat = ChatOpenAI(model=mid, temperature=temperature, max_retries=2)

    def complete(self, request: LlmRequest) -> str:
        text, _usage = self.complete_with_usage(request)
        return text

    def complete_with_usage(self, request: LlmRequest) -> tuple[str, dict[str, Any]]:
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
        usage: dict[str, Any] = {"llm_model": self._model_id}
        meta = getattr(msg, "response_metadata", None) or {}
        tu = meta.get("token_usage") if isinstance(meta, dict) else None
        if isinstance(tu, dict):
            if tu.get("prompt_tokens") is not None:
                usage["llm_input_tokens"] = int(tu["prompt_tokens"])
            if tu.get("completion_tokens") is not None:
                usage["llm_output_tokens"] = int(tu["completion_tokens"])
            if tu.get("total_tokens") is not None:
                usage["llm_total_tokens"] = int(tu["total_tokens"])
        return str(msg.content), usage

    def complete_with_tools(
        self,
        *,
        system: str,
        user: str,
        tools: list[Any],
        max_rounds: int = 4,
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """Multi-turn Chat Completions with tool calls; returns final assistant text + usage + trace rows."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set; use SLAY_LLM_BACKEND=stub for offline runs",
            )
        if not tools:
            text, usage = self.complete_with_usage(
                LlmRequest(system=system, user=user),
            )
            return text, usage, []

        llm_tools = self._chat.bind_tools(tools)
        messages: list[Any] = [
            SystemMessage(content=system),
            HumanMessage(content=user),
        ]
        sub_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {"llm_model": self._model_id}
        by_name = {t.name: t for t in tools}

        def _merge_turn_usage(msg: AIMessage) -> None:
            meta = getattr(msg, "response_metadata", None) or {}
            if not isinstance(meta, dict):
                return
            tu = meta.get("token_usage")
            if not isinstance(tu, dict):
                return
            if tu.get("prompt_tokens") is not None:
                usage["llm_input_tokens"] = int(
                    usage.get("llm_input_tokens", 0) + int(tu["prompt_tokens"]),
                )
            if tu.get("completion_tokens") is not None:
                usage["llm_output_tokens"] = int(
                    usage.get("llm_output_tokens", 0) + int(tu["completion_tokens"]),
                )
            if tu.get("total_tokens") is not None:
                usage["llm_total_tokens"] = int(
                    usage.get("llm_total_tokens", 0) + int(tu["total_tokens"]),
                )

        for round_i in range(max_rounds):
            msg = llm_tools.invoke(messages)
            if not isinstance(msg, AIMessage):
                break
            _merge_turn_usage(msg)
            tcs = list(msg.tool_calls or [])
            if tcs:
                messages.append(msg)
                for tc in tcs:
                    if isinstance(tc, dict):
                        name = tc.get("name")
                        tid = str(tc.get("id") or "")
                        args = tc.get("args")
                    else:
                        name = getattr(tc, "name", None)
                        tid = str(getattr(tc, "id", None) or "")
                        args = getattr(tc, "args", None)
                    if not isinstance(args, dict):
                        args = {}
                    tool = by_name.get(str(name)) if name else None
                    if tool is None:
                        body = (
                            "## TOOL RESULT: Unsupported Tool\n"
                            f"- This tool is not registered ({name!r})."
                        )
                    else:
                        try:
                            body = str(tool.invoke(args))
                        except Exception as e:
                            body = f"## TOOL RESULT: Error\n- {e}"
                    excerpt = body if len(body) <= 2000 else body[:2000] + "…"
                    sub_calls.append(
                        {
                            "tool": name,
                            "arguments": args,
                            "result_excerpt": excerpt,
                            "round": round_i,
                        },
                    )
                    messages.append(ToolMessage(content=body, tool_call_id=tid))
                continue

            text = str(msg.content or "").strip()
            if text:
                return text, usage, sub_calls
            messages.append(msg)

        usage["tool_loop_exhausted"] = True
        return "", usage, sub_calls
