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


def build_turn_key(vm: dict) -> str:
    header = vm.get("header") or {}
    screen = vm.get("screen") or {}
    combat = vm.get("combat")
    if combat:
        return f"combat:{header.get('floor', '?')}:{header.get('turn', '?')}"
    return f"screen:{header.get('floor', '?')}:{screen.get('type', 'NONE')}"


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
        user_message=trace.user_prompt or "",
        assistant_message=trace.response_text or trace.raw_output or "",
    )


def build_ai_sidecar_path(state_log_path: Path) -> Path:
    return state_log_path.with_suffix(".ai.json")


def write_ai_log(state_log_path: Path, trace: AgentTrace) -> None:
    payload = build_persisted_ai_log(trace)
    ai_log_path = build_ai_sidecar_path(state_log_path)
    with ai_log_path.open("w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, indent=2)

