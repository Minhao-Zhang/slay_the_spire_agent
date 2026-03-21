from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from src.agent.schemas import AgentMode, AgentTrace, PersistedAiLog


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def build_state_id(state: dict) -> str:
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_decision_id(state_id: str) -> str:
    prefix = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{state_id}"


def combat_encounter_fingerprint(vm: dict) -> str | None:
    """Stable id for the current combat encounter (distinct fights on the same floor).

    Uses floor plus live monsters (name + max_hp). Returns None if not in combat.
    """
    combat = vm.get("combat")
    if not combat:
        return None
    header = vm.get("header") or {}
    floor = header.get("floor", "?")
    monsters = combat.get("monsters") or []
    parts: list[str] = []
    for m in monsters:
        if m.get("is_gone"):
            continue
        name = str(m.get("name", "?"))
        max_hp = m.get("max_hp", "?")
        parts.append(f"{name}:{max_hp}")
    parts.sort()
    return f"{floor}:" + "|".join(parts) if parts else f"{floor}:empty"


def build_turn_key(vm: dict) -> str:
    """Build a scene identifier for traces and scene-scoped prompt context.

    - In combat: one key per fight (same key for all turns in that fight).
    - Out of combat: one key per (floor, screen type), e.g. MAP, COMBAT_REWARD, GRID.
    """
    header = vm.get("header") or {}
    screen = vm.get("screen") or {}
    combat = vm.get("combat")
    floor = header.get("floor", "?")
    if combat:
        # One scene key per combat; turn is omitted so the whole fight shares the same key.
        return f"COMBAT:{floor}"
    scene_type = screen.get("type", "NONE")
    return f"{scene_type}:{floor}"


def create_trace(vm: dict, state_id: str, agent_mode: AgentMode, system_prompt: str, user_prompt: str) -> AgentTrace:
    header = vm.get("header") or {}
    screen = vm.get("screen") or {}
    return AgentTrace(
        decision_id=build_decision_id(state_id),
        state_id=state_id,
        turn_key=build_turn_key(vm),
        timestamp=utc_now_iso(),
        status="building_prompt",
        agent_mode=agent_mode,
        floor=header.get("floor") if isinstance(header.get("floor"), int) else None,
        turn=header.get("turn") if isinstance(header.get("turn"), int) else None,
        screen_type=screen.get("type", "NONE"),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )


def build_persisted_ai_log(trace: AgentTrace) -> PersistedAiLog:
    return PersistedAiLog(
        decision_id=trace.decision_id,
        state_id=trace.state_id,
        turn_key=trace.turn_key,
        user_message=trace.user_prompt or "",
        assistant_message=trace.response_text or trace.raw_output or "",
        status=trace.status,
        final_decision=trace.final_decision,
        final_decision_sequence=list(trace.final_decision_sequence),
        approval_status=trace.approval_status,
        execution_outcome=trace.execution_outcome,
        latency_ms=trace.latency_ms,
        input_tokens=trace.token_usage.input_tokens,
        output_tokens=trace.token_usage.output_tokens,
        total_tokens=trace.token_usage.total_tokens,
        tool_names=list(trace.tool_names),
        planner_summary=trace.planner_summary,
        combat_plan_generated=trace.combat_plan_generated,
        combat_plan_text_preview=trace.combat_plan_text_preview,
        combat_plan_error=trace.combat_plan_error,
        combat_plan_latency_ms=trace.combat_plan_latency_ms,
        validation_error=trace.validation.error,
        error=trace.error,
    )


def build_ai_sidecar_path(state_log_path: Path) -> Path:
    return state_log_path.with_suffix(".ai.json")


def write_ai_log(state_log_path: Path, trace: AgentTrace) -> None:
    payload = build_persisted_ai_log(trace)
    ai_log_path = build_ai_sidecar_path(state_log_path)
    with ai_log_path.open("w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, indent=2)

