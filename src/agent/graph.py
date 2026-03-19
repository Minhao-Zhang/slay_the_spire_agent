from __future__ import annotations

from copy import deepcopy
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.agent.config import get_agent_config, load_system_prompt
from src.agent.llm_client import LLMClient
from src.agent.policy import parse_agent_output, validate_final_decision
from src.agent.prompt_builder import build_user_prompt
from src.agent.schemas import AgentMode, AgentTrace, ParsedAgentTurn, TraceLlmCall
from src.agent.session_state import TurnConversation, format_executed_action
from src.agent.tool_registry import execute_tool
from src.agent.tracing import create_trace


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
        graph.add_node("build_prompt", self._build_prompt)
        graph.add_node("plan_turn", self._plan_turn)
        graph.add_node("run_agent", self._run_agent)
        graph.add_node("run_tool", self._run_tool)
        graph.add_node("validate_decision", self._validate_decision)
        graph.add_edge(START, "build_prompt")
        graph.add_conditional_edges(
            "build_prompt",
            self._after_build_prompt,
            {
                "plan_turn": "plan_turn",
                "run_agent": "run_agent",
            },
        )
        graph.add_edge("plan_turn", "run_agent")
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

    def _build_prompt(self, state: GraphState) -> GraphState:
        vm = state["vm"]
        turn_key = state["trace"].turn_key
        self.session.set_scene(turn_key)
        self.session.update_strategy_memory(vm)
        if self.llm and self.session.needs_compaction(self.config.history_compact_token_threshold):
            keep_recent = min(self.config.history_keep_recent, max(len(self.session.messages) - 1, 0))
            older_messages = self.session.messages[:-keep_recent] if keep_recent else list(self.session.messages)
            summary = self.llm.summarize_history_compaction(older_messages)
            if summary:
                self.session.compact_history(summary, self.config.history_keep_recent)
        user_prompt = build_user_prompt(
            vm,
            state["state_id"],
            self.session.action_history,
            strategy_memory=self.session.strategy_memory_lines(),
        )
        state["trace"].status = "running"
        state["trace"].user_prompt = user_prompt
        state["messages"] = self.session.messages + [{"role": "user", "content": user_prompt}]
        state["user_prompt"] = user_prompt
        state["previous_response_id"] = None
        return state

    def _after_build_prompt(self, _state: GraphState) -> str:
        return "plan_turn" if self.config.planner_enabled else "run_agent"

    def _plan_turn(self, state: GraphState) -> GraphState:
        vm = state["vm"]
        legal_actions = vm.get("actions") or []
        header = vm.get("header") or {}
        screen = vm.get("screen") or {}
        combat = vm.get("combat") or {}

        priorities: list[str] = []
        if combat:
            priorities.append("Survive this turn first (minimize avoidable incoming damage).")
            if any(str(a.get("command", "")).startswith("END") for a in legal_actions):
                priorities.append("Spend available energy efficiently before ending turn.")
            if any(str(a.get("command", "")).startswith("PLAY ") for a in legal_actions):
                priorities.append("Prefer lines that improve near-term lethal or stabilize scaling.")
        if screen.get("type") == "MAP":
            priorities.append("Balance risk vs reward on pathing using HP, deck strength, and upcoming boss.")
        if not priorities:
            priorities.append("Select the highest-value legal action for the current screen context.")

        planning_summary = (
            f"floor={header.get('floor', '?')} screen={screen.get('type', 'NONE')} "
            f"legal_actions={len(legal_actions)}"
        )
        plan_lines = "\n".join(f"- {line}" for line in priorities[:3])
        plan_text = f"## TURN PLAN\n{plan_lines}\n"
        state["user_prompt"] = f"{plan_text}\n{state['user_prompt']}".strip() + "\n"
        state["messages"] = self.session.messages + [{"role": "user", "content": state["user_prompt"]}]
        state["plan_text"] = planning_summary
        state["trace"].planner_summary = planning_summary
        self._emit_trace(state["trace"])
        return state

    def _run_agent(self, state: GraphState) -> GraphState:
        if not self.ai_enabled or not self.llm:
            state["trace"].status = "disabled"
            state["trace"].error = self.ai_disabled_reason
            return state

        trace = state["trace"]
        stage = "tool_continuation" if any("type" in item for item in state.get("messages", [])) else "proposal"
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
                tool_result = execute_tool(
                    tool_call["name"],
                    state["vm"],
                    tool_call.get("parsed_arguments", {}),
                )
                question = tool_call.get("parsed_arguments", {}).get("question", "").strip()
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
            state["trace"].response_text + f"\n\n[Legacy tool used: {parsed.tool_request.tool_name}]"
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
        graph_state: GraphState = {
            "vm": vm,
            "state_id": state_id,
            "system_prompt": self.system_prompt,
            "trace": trace,
            "tool_roundtrips": 0,
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

