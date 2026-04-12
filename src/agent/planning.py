"""Unified planning phase: LLM combat plan + heuristic non-combat turn priorities.

Used by the LangGraph pipeline between memory retrieval and prompt assembly.
Single-writer session assumptions match ``TurnConversation`` combat plan cache.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from src.agent.config import AgentConfig
from src.agent.llm_client import LLMClient
from src.agent.prompt_builder import COMBAT_PLAN_SYSTEM, build_combat_planning_prompt
from src.agent.schemas import AgentTrace, TraceLlmCall, TraceTokenUsage
from src.agent.session_state import TurnConversation
from src.agent.tracing import combat_encounter_fingerprint
from src.agent.vm_shapes import as_dict, normalize_legal_actions


@dataclass(slots=True)
class PlanningOutcome:
    combat_plan_updated: bool
    non_combat_plan_block: str | None
    planner_summary: str


def _header_combat_turn(header: dict[str, Any]) -> int | None:
    t = header.get("turn")
    if isinstance(t, int):
        return t
    if isinstance(t, str) and t.strip().isdigit():
        return int(t.strip())
    return None


def _merge_token_usage(target: TraceTokenUsage, extra: TraceTokenUsage) -> None:
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
            setattr(target, name, (cur or 0) + new)


def _ensure_combat_plan(
    vm: dict[str, Any],
    trace: AgentTrace,
    session: TurnConversation,
    config: AgentConfig,
    llm: LLMClient | None,
    ai_enabled: bool,
    emit_trace: Callable[[], None],
) -> bool:
    """Generate or refresh combat plan on session. Returns True if a new plan was stored."""
    trace.combat_plan_generated = False
    trace.combat_plan_text_preview = ""
    trace.combat_plan_error = ""
    trace.combat_plan_latency_ms = None
    trace.combat_plan_model_used = ""
    plan_key = "reasoning"
    session.sync_combat_plan_for_vm(vm)
    if not vm.get("combat"):
        return False
    if session.combat_plan_guide:
        trace.combat_plan_text_preview = session.combat_plan_guide[:800]
    if not config.planner_enabled:
        return False
    if not ai_enabled or not llm:
        if not session.combat_plan_guide:
            trace.combat_plan_error = "Combat plan skipped: AI unavailable."
        return False
    fp = combat_encounter_fingerprint(vm)
    if not fp:
        return False
    turn_n = _header_combat_turn(as_dict(vm.get("header")))
    should_generate = False
    if turn_n is None:
        should_generate = not bool(session.combat_plan_guide)
    else:
        should_generate = turn_n == 1 or ((turn_n - 1) % 5 == 0)
        if session.combat_plan_last_turn == turn_n:
            should_generate = False
    if not should_generate:
        return False

    planning_user = build_combat_planning_prompt(
        vm, max_cards_per_section=config.combat_plan_max_cards_per_section
    )
    input_messages = [
        {"role": "system", "content": COMBAT_PLAN_SYSTEM},
        {"role": "user", "content": planning_user},
    ]
    trace.llm_calls.append(
        TraceLlmCall(
            round_index=len(trace.llm_calls) + 1,
            stage="combat_plan",
            input_messages=deepcopy(input_messages),
        )
    )
    emit_trace()
    trace.combat_plan_model_used = (
        config.fast_model if plan_key == "fast" else config.reasoning_model
    )
    try:
        result = llm.generate_combat_plan(
            system_prompt=COMBAT_PLAN_SYSTEM,
            user_content=planning_user,
            max_output_tokens=config.combat_plan_max_output_tokens,
            model_key=plan_key,
        )
    except Exception as exc:  # noqa: BLE001
        trace.combat_plan_error = f"Combat plan failed: {exc}"
        emit_trace()
        return False

    text = (result.get("raw_output") or "").strip()
    usage = result.get("token_usage")
    if isinstance(usage, TraceTokenUsage):
        _merge_token_usage(trace.token_usage, usage)
    trace.combat_plan_latency_ms = result.get("latency_ms")
    if not text:
        trace.combat_plan_error = "Combat plan returned empty text."
        emit_trace()
        return False

    session.set_combat_plan(text, fp, turn_n)
    trace.combat_plan_generated = True
    trace.combat_plan_text_preview = text[:800]
    emit_trace()
    return True


def _non_combat_plan_block(vm: dict[str, Any], *, planner_enabled: bool) -> tuple[str | None, str]:
    """Heuristic priorities for non-combat turns when ``planner_enabled``."""
    if not planner_enabled or vm.get("combat"):
        return None, ""

    legal_actions = normalize_legal_actions(vm.get("actions") or [])
    header = as_dict(vm.get("header"))
    screen = as_dict(vm.get("screen"))

    priorities: list[str] = []
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
    return plan_text, planning_summary


def _combat_planner_summary(vm: dict[str, Any], config: AgentConfig) -> str:
    header = as_dict(vm.get("header"))
    legal_actions = normalize_legal_actions(vm.get("actions") or [])
    return (
        f"floor={header.get('floor', '?')} screen=COMBAT legal_actions={len(legal_actions)} "
        f"planner_enabled={config.planner_enabled}"
    )


def resolve_planning(
    vm: dict[str, Any],
    trace: AgentTrace,
    session: TurnConversation,
    config: AgentConfig,
    llm: LLMClient | None,
    ai_enabled: bool,
    emit_trace: Callable[[], None],
) -> PlanningOutcome:
    """Run combat LLM planning (if applicable) and build non-combat heuristic plan block."""
    combat_updated = _ensure_combat_plan(vm, trace, session, config, llm, ai_enabled, emit_trace)
    block, nc_summary = _non_combat_plan_block(vm, planner_enabled=config.planner_enabled)

    if vm.get("combat"):
        summary = _combat_planner_summary(vm, config)
    else:
        summary = nc_summary

    trace.planner_summary = summary
    emit_trace()
    return PlanningOutcome(
        combat_plan_updated=combat_updated,
        non_combat_plan_block=block,
        planner_summary=summary,
    )
