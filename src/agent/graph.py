from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.agent.config import get_agent_config, load_system_prompt
from src.agent.memory import MemoryStore, build_context_tags
from src.agent.memory.types import RetrievalHit
from src.agent.llm_client import LLMClient
from src.agent.planning import resolve_planning
from src.agent.reasoning_budget import ReasoningBudgetRouter
from src.agent.policy import parse_agent_output, validate_final_decision
from src.agent.prompt_builder import build_user_prompt
from src.agent.schemas import AgentMode, AgentTrace, ParsedAgentTurn, TraceLlmCall, TraceTokenUsage
from src.agent.session_state import TurnConversation, format_executed_action
from src.agent.tool_registry import execute_tool, list_function_tools_for_context
from src.agent.tracing import create_trace
from src.agent.vm_shapes import as_dict
from src.repo_paths import PACKAGE_ROOT


class GraphState(TypedDict, total=False):
    vm: dict[str, Any]
    state_id: str
    system_prompt: str
    user_prompt: str
    messages: list[dict[str, Any]]
    parsed_turn: ParsedAgentTurn | None
    trace: AgentTrace
    tool_roundtrips: int
    tool_calls: list[dict[str, Any]]
    previous_response_id: str | None
    plan_text: str
    error: str
    turn_model_key: str | None
    turn_reasoning_effort: str | None
    tool_filter: str | None
    memory_hits: list[RetrievalHit] | None
    non_combat_plan_block: str | None
    planning_context_block: str | None


class SpireDecisionAgent:
    def __init__(self):
        self.config = get_agent_config()
        self.system_prompt = load_system_prompt()
        self.session = TurnConversation()
        self.llm = LLMClient(self.config) if self.config.enabled else None
        self.ai_enabled = False
        self.ai_status = "disabled"
        self.ai_api_style = ""
        if not self.config.api_key:
            self.ai_disabled_reason = "LLM mis-configured: missing LLM_API_KEY."
            self.ai_status = "disabled"
        elif not self.config.reasoning_model:
            self.ai_disabled_reason = "LLM mis-configured: missing LLM_MODEL_REASONING."
            self.ai_status = "disabled"
        elif self.llm:
            self.ai_disabled_reason = "Checking LLM configuration..."
            self.ai_status = "checking"
        else:
            self.ai_disabled_reason = "LLM is not configured."
            self.ai_status = "disabled"
        self.memory_store = MemoryStore(
            memory_dir=self.config.resolved_memory_dir(),
            strategy_dir=self.config.resolved_strategy_dir(),
            expert_guides_dir=self.config.resolved_expert_guides_dir(),
        )
        self.budget_router = ReasoningBudgetRouter(self.config)
        self._cached_memory_hits: list[RetrievalHit] | None = None
        self._cached_planning_block: str | None = None
        self.graph = self._build_graph()

    def set_ai_unavailable(self, status: str, reason: str) -> None:
        self.ai_enabled = False
        self.ai_status = status
        self.ai_disabled_reason = reason

    def initialize_ai_runtime(self) -> dict[str, str | bool]:
        if not self.llm:
            self.ai_enabled = False
            self.ai_status = "disabled"
            return {
                "enabled": False,
                "status": self.ai_status,
                "api_style": "",
                "message": self.ai_disabled_reason,
            }

        self.llm.check_api_capabilities()
        self.ai_enabled = self.llm.available
        self.ai_api_style = self.llm.api_style or ""
        if self.ai_enabled:
            self.ai_disabled_reason = ""
            self.ai_status = "ready"
            return {
                "enabled": True,
                "status": self.ai_status,
                "api_style": self.ai_api_style,
                "message": f"LLM connected via {self.ai_api_style}.",
            }

        self.ai_disabled_reason = self.llm.disabled_reason or "LLM is unavailable."
        self.ai_status = "failed" if self.llm.capability_state == "failed" else "disabled"
        return {
            "enabled": False,
            "status": self.ai_status,
            "api_style": "",
            "message": self.ai_disabled_reason,
        }

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("retrieve_memory", self._retrieve_memory)
        graph.add_node("resolve_planning", self._resolve_planning_node)
        graph.add_node("assemble_prompt", self._assemble_prompt)
        graph.add_node("run_agent", self._run_agent)
        graph.add_node("run_tool", self._run_tool)
        graph.add_node("validate_decision", self._validate_decision)
        graph.add_edge(START, "retrieve_memory")
        graph.add_edge("retrieve_memory", "resolve_planning")
        graph.add_edge("resolve_planning", "assemble_prompt")
        graph.add_edge("assemble_prompt", "run_agent")
        graph.add_conditional_edges(
            "run_agent",
            self._after_agent,
            {
                "run_tool": "run_tool",
                "validate_decision": "validate_decision",
                "end": END,
            },
        )
        graph.add_edge("run_tool", "run_agent")
        graph.add_edge("validate_decision", END)
        return graph.compile()

    def _emit_trace(self, trace: AgentTrace) -> None:
        trace.update_seq += 1
        if self.trace_callback:
            self.trace_callback(trace)

    @staticmethod
    def _merge_token_usage(target: TraceTokenUsage, extra: TraceTokenUsage | None) -> None:
        if not extra:
            return
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "uncached_input_tokens",
        ):
            cur = getattr(target, name)
            new = getattr(extra, name, None)
            if new is not None:
                setattr(target, name, (cur or 0) + int(new))

    @staticmethod
    def _hit_stable_id(hit: RetrievalHit) -> str:
        if hit.layer == "strategy":
            return f"strategy:{Path(hit.source_ref).name}"
        if hit.layer == "expert":
            return f"expert:{Path(hit.source_ref).name}"
        if hit.layer == "procedural":
            return f"procedural:{hit.source_ref}"
        return f"episodic:{hit.source_ref}"

    @staticmethod
    def _parse_retrieval_json(text: str) -> dict[str, Any] | None:
        s = text.strip()
        start = s.find("{")
        end = s.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None

    @staticmethod
    def _compact_vm_for_retrieval(vm: dict[str, Any]) -> dict[str, Any]:
        header = as_dict(vm.get("header"))
        screen = as_dict(vm.get("screen"))
        inv = as_dict(vm.get("inventory"))
        deck = inv.get("deck") if isinstance(inv.get("deck"), list) else []
        combat = vm.get("combat") if isinstance(vm.get("combat"), dict) else None
        enemies: list[str] = []
        if combat:
            for m in combat.get("monsters") or []:
                if isinstance(m, dict) and not m.get("is_gone"):
                    enemies.append(str(m.get("name", "")))
        return {
            "floor": header.get("floor"),
            "act": header.get("act"),
            "turn": header.get("turn"),
            "class": header.get("class"),
            "screen": screen.get("type"),
            "hp": header.get("current_hp"),
            "max_hp": header.get("max_hp"),
            "gold": header.get("gold"),
            "deck_size": len(deck),
            "enemies": enemies[:8],
        }

    def _retrieval_planning_filter(
        self,
        vm: dict[str, Any],
        trace: AgentTrace,
        pool_hits: list[RetrievalHit],
    ) -> tuple[list[RetrievalHit], str | None]:
        prompt_path = PACKAGE_ROOT / "agent" / "prompts" / "retrieval_agent_prompt.md"
        try:
            system = prompt_path.read_text(encoding="utf-8").strip()
        except OSError:
            system = (
                "You select knowledge entry IDs and return JSON "
                'with selected_entry_ids, situation_note, planning_note.'
            )
        index = self.memory_store.knowledge_index_entries()[:220]
        payload = {
            "vm_summary": self._compact_vm_for_retrieval(vm),
            "knowledge_index": index,
        }
        user_msg = json.dumps(payload, ensure_ascii=False, default=str)
        trace.llm_calls.append(
            TraceLlmCall(
                round_index=len(trace.llm_calls) + 1,
                stage="retrieval_planning",
                input_messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
            )
        )
        self._emit_trace(trace)
        if not self.llm:
            return pool_hits[: self.config.max_memory_hits], None
        result = self.llm.generate_plain_completion(
            system_prompt=system,
            user_content=user_msg,
            model_key="fast",
            max_output_tokens=1200,
            reasoning_effort="low",
        )
        usage = result.get("token_usage")
        if isinstance(usage, TraceTokenUsage):
            self._merge_token_usage(trace.token_usage, usage)
        raw = str(result.get("raw_output") or "")
        data = self._parse_retrieval_json(raw)
        ids_raw = data.get("selected_entry_ids") if data else None
        situation = str((data or {}).get("situation_note") or "").strip()
        planning = str((data or {}).get("planning_note") or "").strip()
        if not isinstance(ids_raw, list):
            return pool_hits[: self.config.max_memory_hits], None
        want = {str(x).strip() for x in ids_raw if str(x).strip()}
        by_id = {self._hit_stable_id(h): h for h in pool_hits}
        filtered = [by_id[i] for i in want if i in by_id]
        if not filtered:
            filtered = pool_hits[: self.config.max_memory_hits]
        else:
            filtered = filtered[: self.config.max_memory_hits]
        block: str | None = None
        if situation or planning:
            parts = []
            if situation:
                parts.append(f"**Situation:** {situation}")
            if planning:
                parts.append(f"**Planning note:** {planning}")
            block = "## Context from planning agent\n" + "\n".join(parts)
        return filtered, block

    def _retrieve_memory(self, state: GraphState) -> GraphState:
        vm = state["vm"]
        trace = state["trace"]
        profile = self.budget_router.resolve(vm)
        state["turn_model_key"] = profile.model_key
        state["turn_reasoning_effort"] = profile.reasoning_effort
        state["tool_filter"] = profile.tool_filter
        trace.reasoning_profile_name = profile.name
        trace.reasoning_effort_used = profile.reasoning_effort
        trace.retrieval_mode_used = profile.retrieval_mode

        if not self.config.memory_retrieval_enabled or profile.retrieval_mode == "skip":
            state["memory_hits"] = None
            trace.lessons_retrieved = 0
            state["planning_context_block"] = None
            return state

        if profile.retrieval_mode == "reuse":
            if self._cached_memory_hits is None:
                tags = build_context_tags(vm)
                self._cached_memory_hits = self.memory_store.retrieve(
                    tags,
                    max_results=self.config.max_memory_hits,
                    char_budget=self.config.memory_char_budget,
                    min_procedural_confidence=self.config.min_procedural_confidence,
                )
                self._cached_planning_block = None
            state["memory_hits"] = self._cached_memory_hits
            state["planning_context_block"] = self._cached_planning_block
            trace.lessons_retrieved = len(state["memory_hits"] or [])
            return state

        tags = build_context_tags(vm)
        pool_max = (
            max(self.config.max_memory_hits * 3, 24)
            if profile.retrieval_mode == "full"
            else self.config.max_memory_hits
        )
        pool_budget = (
            max(self.config.memory_char_budget, 12_000)
            if profile.retrieval_mode == "full"
            else self.config.memory_char_budget
        )
        hits = self.memory_store.retrieve(
            tags,
            max_results=pool_max,
            char_budget=pool_budget,
            min_procedural_confidence=self.config.min_procedural_confidence,
        )
        planning_block: str | None = None
        if profile.retrieval_mode == "full" and self.llm and self.ai_enabled and hits:
            try:
                hits, planning_block = self._retrieval_planning_filter(vm, trace, hits)
            except Exception:  # noqa: BLE001
                hits = hits[: self.config.max_memory_hits]
                planning_block = None
        else:
            hits = hits[: self.config.max_memory_hits]

        self._cached_memory_hits = hits
        self._cached_planning_block = planning_block
        state["memory_hits"] = hits
        state["planning_context_block"] = planning_block
        trace.lessons_retrieved = len(hits)
        return state

    def _resolve_planning_node(self, state: GraphState) -> GraphState:
        trace = state["trace"]
        outcome = resolve_planning(
            state["vm"],
            trace,
            self.session,
            self.config,
            self.llm,
            self.ai_enabled,
            emit_trace=lambda: self._emit_trace(trace),
        )
        state["non_combat_plan_block"] = outcome.non_combat_plan_block
        state["plan_text"] = outcome.planner_summary
        return state

    def _assemble_prompt(self, state: GraphState) -> GraphState:
        vm = state["vm"]
        turn_key = state["trace"].turn_key
        self.session.set_scene(turn_key)
        self.session.update_strategy_memory(vm)
        tokenizer_model = (self.config.history_tokenizer_model or self.config.fast_model).strip()
        if self.llm and self.session.needs_compaction(
            self.config.history_compact_token_threshold,
            self.system_prompt,
            tokenizer_model,
        ):
            msgs = self.session.messages
            keep_recent = min(self.config.history_keep_recent, len(msgs))
            older_messages = msgs[:-keep_recent] if keep_recent else list(msgs)
            if not older_messages and len(msgs) > 1:
                keep_recent = max(1, len(msgs) // 2)
                older_messages = msgs[:-keep_recent]
            max_chars = self.config.history_compaction_transcript_max_chars
            summary = ""
            if older_messages:
                summary = self.llm.summarize_history_compaction(
                    older_messages,
                    max_transcript_chars=max_chars,
                )
            if not summary and older_messages:
                summary = self.llm.summarize_history_compaction(
                    older_messages,
                    max_transcript_chars=max(50_000, max_chars // 2),
                )
            if summary:
                self.session.compact_history(summary, keep_recent)
            elif older_messages:
                self.session.compact_history_fallback(keep_recent)

        memory_hits = state.get("memory_hits")
        user_prompt = build_user_prompt(
            vm,
            state["state_id"],
            self.session.action_history,
            strategy_memory=self.session.strategy_memory_lines(),
            combat_plan_guide=self.session.combat_plan_guide or None,
            prompt_profile=self.config.prompt_profile,
            memory_hits=memory_hits,
        )
        prefix_parts: list[str] = []
        plan_ctx = state.get("planning_context_block")
        if plan_ctx:
            prefix_parts.append(plan_ctx)
        nc = state.get("non_combat_plan_block")
        if nc:
            prefix_parts.append(nc)
        if prefix_parts:
            user_prompt = "\n\n".join(prefix_parts) + "\n\n" + user_prompt.strip() + "\n"

        state["trace"].status = "running"
        state["trace"].user_prompt = user_prompt
        state["messages"] = self.session.messages + [{"role": "user", "content": user_prompt}]
        state["user_prompt"] = user_prompt
        state["previous_response_id"] = None
        return state

    def _run_agent(self, state: GraphState) -> GraphState:
        if not self.ai_enabled or not self.llm:
            state["trace"].status = "disabled"
            state["trace"].error = self.ai_disabled_reason
            return state

        trace = state["trace"]
        if state.get("turn_model_key") is None:
            profile = self.budget_router.resolve(state["vm"])
            state["turn_model_key"] = profile.model_key
            state["turn_reasoning_effort"] = profile.reasoning_effort
            state["tool_filter"] = profile.tool_filter
            trace.reasoning_profile_name = profile.name
            trace.reasoning_effort_used = profile.reasoning_effort
            trace.retrieval_mode_used = profile.retrieval_mode
        model_key = state["turn_model_key"] or "reasoning"
        func_tools = list_function_tools_for_context(state.get("tool_filter"))
        tools_arg = func_tools if func_tools else None
        trace.llm_turn_model_key = model_key
        trace.llm_model_used = (
            self.llm.model_name_for_key(model_key)
            if self.llm
            else (self.config.fast_model if model_key == "fast" else self.config.reasoning_model)
        )
        stage = (
            "tool_continuation"
            if any(isinstance(item, dict) and "type" in item for item in state.get("messages", []))
            else "proposal"
        )
        trace.llm_calls.append(
            TraceLlmCall(
                round_index=len(trace.llm_calls) + 1,
                stage=stage,
                previous_response_id=state.get("previous_response_id"),
                input_messages=deepcopy(state.get("messages", [])),
            )
        )
        trace.raw_output = ""
        trace.reasoning_text = ""
        trace.reasoning_summary_text = ""
        trace.response_text = ""
        state["tool_calls"] = []

        def on_delta(delta: str) -> None:
            trace.raw_output += delta
            parsed = parse_agent_output(trace.raw_output)
            trace.reasoning_text = parsed.reasoning
            trace.response_text = trace.raw_output
            self._emit_trace(trace)

        def on_tool(tool_name: str) -> None:
            trace.tool_names.append(tool_name)
            trace.response_text = (trace.response_text + f"\n\n[Tool requested: {tool_name}]").strip()
            self._emit_trace(trace)

        try:
            result = self.llm.run_streaming_turn(
                system_prompt=state["system_prompt"],
                input_items=state["messages"],
                previous_response_id=state.get("previous_response_id"),
                on_delta=on_delta,
                on_tool=on_tool,
                model_key=model_key,
                reasoning_effort=state.get("turn_reasoning_effort"),
                function_tools=tools_arg,
            )
        except Exception as exc:  # noqa: BLE001
            trace.status = "error"
            trace.error = f"LLM call failed: {exc}"
            self._emit_trace(trace)
            return state
        parsed_turn = parse_agent_output(result["raw_output"])
        trace.raw_output = result["raw_output"]
        trace.reasoning_text = result["reasoning_summary_text"] or parsed_turn.reasoning
        trace.reasoning_summary_text = result["reasoning_summary_text"]
        trace.response_text = result["raw_output"]
        trace.latency_ms = result["latency_ms"]
        trace.token_usage = result["token_usage"]
        state["parsed_turn"] = parsed_turn
        state["tool_calls"] = result["tool_calls"]
        state["previous_response_id"] = result["response_id"]
        self._emit_trace(trace)
        return state

    def _after_agent(self, state: GraphState) -> str:
        parsed = state.get("parsed_turn")
        if state["trace"].status in {"disabled", "error"}:
            return "end"
        if state.get("tool_calls") and state.get("tool_roundtrips", 0) < self.config.max_tool_roundtrips:
            return "run_tool"
        if parsed and parsed.tool_request and state.get("tool_roundtrips", 0) < self.config.max_tool_roundtrips:
            return "run_tool"
        return "validate_decision"

    def _run_tool(self, state: GraphState) -> GraphState:
        tool_calls = state.get("tool_calls") or []
        parsed = state.get("parsed_turn")

        if tool_calls:
            tool_outputs: list[dict[str, Any]] = []
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                raw_args = tool_call.get("parsed_arguments", {})
                parsed_args = raw_args if isinstance(raw_args, dict) else {}
                tool_result = execute_tool(
                    tool_call["name"],
                    state["vm"],
                    parsed_args,
                )
                question = str(parsed_args.get("question", "") or "").strip()
                content = tool_result if not question else f"{question}\n\n{tool_result}"
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.get("call_id") or tool_call["id"],
                        "output": content,
                    }
                )
                state["trace"].response_text = (
                    state["trace"].response_text + f"\n\n[Tool used: {tool_call['name']}]"
                ).strip()
            state["messages"] = tool_outputs
            state["tool_roundtrips"] = state.get("tool_roundtrips", 0) + len(tool_calls)
            state["tool_calls"] = []
            self._emit_trace(state["trace"])
            return state

        if not parsed or not parsed.tool_request:
            return state

        tool_result = execute_tool(parsed.tool_request.tool_name, state["vm"], {"question": parsed.tool_request.question})
        state["trace"].tool_names.append(parsed.tool_request.tool_name)
        state["messages"].append({"role": "user", "content": tool_result})
        state["previous_response_id"] = None
        state["tool_roundtrips"] = state.get("tool_roundtrips", 0) + 1
        state["trace"].response_text = (
            state["trace"].response_text + f"\n\n[Tool used: {parsed.tool_request.tool_name}]"
        ).strip()
        self._emit_trace(state["trace"])
        return state

    def _validate_decision(self, state: GraphState) -> GraphState:
        parsed = state.get("parsed_turn") or ParsedAgentTurn()
        validation = validate_final_decision(parsed.final_decision, state["vm"].get("actions", []))
        state["trace"].parsed_proposal = (
            parsed.final_decision.model_dump() if parsed.final_decision else None
        )
        state["trace"].validation = validation
        if validation.valid:
            state["trace"].status = "awaiting_approval"
            state["trace"].final_decision = validation.matched_command
            # Store the full token-based sequence from the LLM for queued execution
            if parsed.final_decision and parsed.final_decision.chosen_commands:
                state["trace"].final_decision_sequence = list(parsed.final_decision.chosen_commands)
            else:
                state["trace"].final_decision_sequence = (
                    [validation.matched_command] if validation.matched_command else []
                )
        else:
            state["trace"].status = "invalid"
            state["trace"].error = validation.error
        self._emit_trace(state["trace"])
        return state

    def propose(
        self,
        vm: dict[str, Any],
        state_id: str,
        agent_mode: AgentMode,
        trace_callback=None,
    ) -> AgentTrace:
        self.trace_callback = trace_callback
        trace = create_trace(vm, state_id, agent_mode, self.system_prompt, "")
        trace.prompt_profile = self.config.prompt_profile
        self._cached_memory_hits = None
        self._cached_planning_block = None
        graph_state: GraphState = {
            "vm": vm,
            "state_id": state_id,
            "system_prompt": self.system_prompt,
            "trace": trace,
            "tool_roundtrips": 0,
            "turn_model_key": None,
            "turn_reasoning_effort": None,
            "tool_filter": None,
            "planning_context_block": None,
        }
        result = self.graph.invoke(graph_state)
        if result["trace"].raw_output:
            self.session.append_user(result["user_prompt"])
            self.session.append_assistant(result["trace"].raw_output)
        return result["trace"]

    def remember_executed_action(
        self,
        trace: AgentTrace | None,
        action: str,
        legal_actions: list[dict[str, Any]] | None = None,
    ) -> None:
        if not action:
            return
        if trace and trace.turn_key == self.session.scene_key:
            self.session.remember_action(format_executed_action(action, legal_actions))

