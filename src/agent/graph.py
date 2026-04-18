from __future__ import annotations

from copy import deepcopy
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.agent.config import (
    MAX_MEMORY_HITS,
    MEMORY_CHAR_BUDGET,
    MIN_PROCEDURAL_CONFIDENCE,
    get_agent_config,
    load_system_prompt,
)
from src.agent.memory import MemoryStore, build_context_tags
from src.agent.memory.types import RetrievalHit
from src.agent.llm_client import LLMClient
from src.agent.llm_context import LlmCallContext
from src.agent.planning import resolve_combat_planning
from src.agent.policy import parse_agent_output, validate_final_decision
from src.agent.prompt_builder import build_user_prompt
from src.agent.schemas import AgentMode, AgentTrace, ParsedAgentTurn, TraceLlmCall, TraceTokenUsage
from src.agent.session_state import TurnConversation, format_executed_action
from src.agent.strategist import hit_stable_id, run_strategist_llm
from src.agent.tool_registry import execute_tool, list_function_tools_for_context, tool_filter_for_context
from src.agent.tracing import create_trace
from src.agent.vm_shapes import as_dict, normalize_legal_actions
from src.observability.langfuse_client import langfuse_trace_id_for_decision_id


def _reward_flow_label_for_choose(action: str, legal_actions: list[dict[str, Any]] | None) -> str:
    normalized = action.strip()
    for candidate in normalize_legal_actions(legal_actions or []):
        command = str(candidate.get("command", "")).strip()
        if command != normalized:
            continue
        label = str(candidate.get("label", "")).strip()
        if label:
            return f"Opened: {label}"
    return f"Chose {normalized}"


def _resolve_chosen_card_label_for_take(action: str, legal_actions: list[dict[str, Any]] | None) -> str:
    normalized = action.strip()
    for candidate in normalize_legal_actions(legal_actions or []):
        command = str(candidate.get("command", "")).strip()
        if command != normalized:
            continue
        label = str(candidate.get("label", "")).strip()
        return label if label else normalized
    return normalized


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
    tool_filter: str | None
    memory_hits: list[RetrievalHit] | None
    non_combat_plan_block: str | None
    planning_context_block: str | None
    strategist_output: dict[str, Any] | None


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
            self.ai_disabled_reason = "LLM mis-configured: missing API_KEY."
            self.ai_status = "disabled"
        elif not self.config.decision_model:
            self.ai_disabled_reason = "LLM mis-configured: missing DECISION_MODEL."
            self.ai_status = "disabled"
        elif self.llm:
            self.ai_disabled_reason = "Checking LLM configuration..."
            self.ai_status = "checking"
        else:
            self.ai_disabled_reason = "LLM is not configured."
            self.ai_status = "disabled"
        self.memory_store = MemoryStore(
            memory_dir=self.config.resolved_memory_dir(),
            knowledge_dir=self.config.resolved_knowledge_dir(),
        )
        self._cached_memory_hits: list[RetrievalHit] | None = None
        self._cached_planning_block: str | None = None
        self._cached_non_combat_plan_block: str | None = None
        self.graph = self._build_graph()
        self.persistence_run_id: str | None = None
        self.persistence_langfuse_session_id: str | None = None
        self.persistence_frame_id: str | None = None
        self.persistence_event_index: int | None = None

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
        graph.add_node("run_strategist", self._run_strategist)
        graph.add_node("resolve_combat_plan", self._resolve_combat_plan_node)
        graph.add_node("assemble_prompt", self._assemble_prompt)
        graph.add_node("run_agent", self._run_agent)
        graph.add_node("run_tool", self._run_tool)
        graph.add_node("validate_decision", self._validate_decision)
        graph.add_edge(START, "run_strategist")
        graph.add_edge("run_strategist", "resolve_combat_plan")
        graph.add_edge("resolve_combat_plan", "assemble_prompt")
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

    def _llm_ctx(self, state: GraphState, *, stage: str, round_index: int) -> LlmCallContext | None:
        rid = self.persistence_run_id
        sid = (self.persistence_langfuse_session_id or "").strip() or None
        if not rid and not sid:
            return None
        vm = state["vm"]
        header = as_dict(vm.get("header"))
        effort = (
            (self.config.decision_reasoning_effort or "").strip().lower()
            if stage == "decision"
            else (self.config.support_reasoning_effort or "").strip().lower()
        )
        trace = state["trace"]
        tags = {
            "floor": header.get("floor"),
            "character": header.get("class"),
            "act": header.get("act"),
            "agent_mode": str(trace.agent_mode),
        }
        return LlmCallContext(
            run_id=rid,
            langfuse_session_id=sid,
            frame_id=self.persistence_frame_id,
            event_index=self.persistence_event_index,
            state_id=state["state_id"],
            client_decision_id=trace.decision_id,
            turn_key=trace.turn_key,
            stage=stage,
            round_index=round_index,
            prompt_profile=self.config.prompt_profile,
            experiment_id=self.config.experiment_id,
            langfuse_trace_id=trace.langfuse_trace_id or None,
            reasoning_effort=effort or None,
            mirror_llm_to_sql=bool(rid),
            tags={k: v for k, v in tags.items() if v is not None},
        )

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

    def _run_strategist(self, state: GraphState) -> GraphState:
        vm = state["vm"]
        trace = state["trace"]
        state["tool_filter"] = tool_filter_for_context(vm)

        same_scene = self.session.scene_key is not None and self.session.scene_key == trace.turn_key
        if same_scene and self._cached_memory_hits is not None:
            state["memory_hits"] = self._cached_memory_hits
            state["planning_context_block"] = self._cached_planning_block
            state["non_combat_plan_block"] = self._cached_non_combat_plan_block
            hits = state["memory_hits"] or []
            trace.lessons_retrieved = len(hits)
            trace.retrieved_lesson_ids = [hit_stable_id(h) for h in hits]
            trace.strategist_ran = False
            state["strategist_output"] = None
            return state

        tags = build_context_tags(vm)
        pool_max = max(MAX_MEMORY_HITS * 3, 24)
        pool_budget = max(MEMORY_CHAR_BUDGET, 12_000)
        pool_hits = self.memory_store.retrieve(
            tags,
            max_results=pool_max,
            char_budget=pool_budget,
            min_procedural_confidence=MIN_PROCEDURAL_CONFIDENCE,
        )
        knowledge_index = self.memory_store.knowledge_index_entries()[:220]

        if not self.llm or not self.ai_enabled:
            hits = pool_hits[:MAX_MEMORY_HITS]
            self._cached_memory_hits = hits
            self._cached_planning_block = None
            self._cached_non_combat_plan_block = None
            state["memory_hits"] = hits
            state["planning_context_block"] = None
            state["non_combat_plan_block"] = None
            state["strategist_output"] = None
            trace.lessons_retrieved = len(hits)
            trace.retrieved_lesson_ids = [hit_stable_id(h) for h in hits]
            trace.strategist_ran = False
            return state

        outcome = run_strategist_llm(
            vm=vm,
            trace=trace,
            session=self.session,
            knowledge_index=knowledge_index,
            pool_hits=pool_hits,
            config=self.config,
            llm=self.llm,
            max_hits=MAX_MEMORY_HITS,
            emit_trace=lambda: self._emit_trace(trace),
            llm_call_context=self._llm_ctx(state, stage="strategist", round_index=len(trace.llm_calls) + 1),
        )
        self.session.update_strategy_notes(outcome.strategy_update)
        self._cached_memory_hits = outcome.hits
        self._cached_planning_block = outcome.planning_context_block
        self._cached_non_combat_plan_block = outcome.non_combat_plan_block
        state["memory_hits"] = outcome.hits
        state["planning_context_block"] = outcome.planning_context_block
        state["non_combat_plan_block"] = outcome.non_combat_plan_block
        state["strategist_output"] = outcome.raw_parsed
        trace.lessons_retrieved = len(outcome.hits)
        trace.retrieved_lesson_ids = [hit_stable_id(h) for h in outcome.hits]
        trace.strategist_ran = True
        return state

    def _resolve_combat_plan_node(self, state: GraphState) -> GraphState:
        trace = state["trace"]
        outcome = resolve_combat_planning(
            state["vm"],
            trace,
            self.session,
            self.config,
            self.llm,
            self.ai_enabled,
            emit_trace=lambda: self._emit_trace(trace),
            llm_call_context=self._llm_ctx(state, stage="combat_plan", round_index=len(trace.llm_calls) + 1),
        )
        # Strategist owns non-combat plan; do not overwrite.
        state["plan_text"] = outcome.planner_summary
        return state

    def _assemble_prompt(self, state: GraphState) -> GraphState:
        vm = state["vm"]
        turn_key = state["trace"].turn_key
        self.session.set_scene(turn_key)
        screen_type = (as_dict(state["vm"].get("screen"))).get("type", "")
        if screen_type == "COMBAT_REWARD":
            floor = as_dict(state["vm"].get("header")).get("floor", "?")
            self.session.open_reward_flow(f"{floor}:{state['state_id']}")
        tokenizer_model = self.config.decision_model.strip()
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
            from src.agent.config import HISTORY_COMPACTION_MAX_CHARS

            max_chars = HISTORY_COMPACTION_MAX_CHARS
            summary = ""
            compact_ctx = self._llm_ctx(state, stage="compactor", round_index=len(state["trace"].llm_calls) + 1)
            if older_messages:
                summary = self.llm.summarize_history_compaction(
                    older_messages,
                    max_transcript_chars=max_chars,
                    call_context=compact_ctx,
                )
            if not summary and older_messages:
                summary = self.llm.summarize_history_compaction(
                    older_messages,
                    max_transcript_chars=max(50_000, max_chars // 2),
                    call_context=compact_ctx,
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
            run_journal=list(self.session.run_journal),
            strategy_notes=self.session.strategy_notes_lines(),
            combat_plan_guide=self.session.combat_plan_guide or None,
            prompt_profile=self.config.prompt_profile,
            memory_hits=memory_hits,
            reward_flow=self.session.reward_flow_ledger or None,
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
        if state.get("tool_filter") is None:
            state["tool_filter"] = tool_filter_for_context(state["vm"])
        effort = (self.config.decision_reasoning_effort or "medium").strip().lower()
        trace.reasoning_effort_used = effort
        trace.llm_model_used = self.config.decision_model
        func_tools = list_function_tools_for_context(state.get("tool_filter"))
        tools_arg = func_tools if func_tools else None
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
                llm_role="decision",
                reasoning_effort=effort,
                function_tools=tools_arg,
                call_context=self._llm_ctx(
                    state,
                    stage="decision",
                    round_index=len(trace.llm_calls),
                ),
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
        trace.experiment_tag = self.config.experiment_tag
        trace.experiment_id = self.config.experiment_id
        trace.deck_size = len((vm.get("inventory") or {}).get("deck") or [])
        trace.langfuse_trace_id = langfuse_trace_id_for_decision_id(trace.decision_id)
        graph_state: GraphState = {
            "vm": vm,
            "state_id": state_id,
            "system_prompt": self.system_prompt,
            "trace": trace,
            "tool_roundtrips": 0,
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

        if trace:
            screen = str(trace.screen_type or "").upper()
            cmd = action.strip().upper()
            if screen == "COMBAT_REWARD":
                if cmd.startswith("CHOOSE"):
                    self.session.append_reward_flow(_reward_flow_label_for_choose(action, legal_actions))
                elif cmd == "PROCEED":
                    self.session.close_reward_flow()
            elif screen == "CARD_REWARD":
                if cmd == "SKIP":
                    self.session.append_reward_flow("Skipped card reward (no card taken)")
                elif cmd.startswith("CHOOSE"):
                    card_label = _resolve_chosen_card_label_for_take(action, legal_actions)
                    self.session.append_reward_flow(f"Took card: {card_label}")
