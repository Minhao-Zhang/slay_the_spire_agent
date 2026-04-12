from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

RUN_END_SNAPSHOT_FILENAME = "run_end_snapshot.json"

from src.agent.schemas import AgentMode, AgentTrace, PersistedAiLog
from src.agent.vm_shapes import as_dict


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
    if not combat or not isinstance(combat, dict):
        return None
    header = as_dict(vm.get("header"))
    floor = header.get("floor", "?")
    monsters = combat.get("monsters") or []
    parts: list[str] = []
    for m in monsters:
        if not isinstance(m, dict):
            continue
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
    header = as_dict(vm.get("header"))
    screen = as_dict(vm.get("screen"))
    combat = vm.get("combat")
    floor = header.get("floor", "?")
    if combat:
        # One scene key per combat; turn is omitted so the whole fight shares the same key.
        return f"COMBAT:{floor}"
    scene_type = screen.get("type", "NONE")
    return f"{scene_type}:{floor}"


def create_trace(vm: dict, state_id: str, agent_mode: AgentMode, system_prompt: str, user_prompt: str) -> AgentTrace:
    header = as_dict(vm.get("header"))
    screen = as_dict(vm.get("screen"))
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
        cached_input_tokens=trace.token_usage.cached_input_tokens,
        uncached_input_tokens=trace.token_usage.uncached_input_tokens,
        tool_names=list(trace.tool_names),
        planner_summary=trace.planner_summary,
        combat_plan_generated=trace.combat_plan_generated,
        combat_plan_text_preview=trace.combat_plan_text_preview,
        combat_plan_error=trace.combat_plan_error,
        combat_plan_latency_ms=trace.combat_plan_latency_ms,
        combat_plan_model_used=trace.combat_plan_model_used,
        validation_error=trace.validation.error,
        error=trace.error,
        prompt_profile=trace.prompt_profile,
        llm_model_used=trace.llm_model_used,
        llm_turn_model_key=trace.llm_turn_model_key,
        reasoning_profile_name=trace.reasoning_profile_name,
        reasoning_effort_used=trace.reasoning_effort_used,
        lessons_retrieved=trace.lessons_retrieved,
        retrieval_mode_used=trace.retrieval_mode_used,
    )


def build_ai_sidecar_path(state_log_path: Path) -> Path:
    return state_log_path.with_suffix(".ai.json")


def build_vm_summary(
    vm: dict[str, Any],
    raw_envelope: dict[str, Any],
    *,
    state_id: str,
    event_index: int,
) -> dict[str, Any]:
    """Compact snapshot for logging and metrics (from VM + raw CommunicationMod envelope)."""
    inner = raw_envelope.get("state", raw_envelope)
    game = inner.get("game_state") if isinstance(inner, dict) else None
    if not isinstance(game, dict):
        game = {}

    screen = as_dict(vm.get("screen"))
    header = as_dict(vm.get("header"))
    combat_vm = vm.get("combat")
    in_combat = bool(combat_vm and isinstance(combat_vm, dict))

    floor = game.get("floor", header.get("floor"))
    act = game.get("act", header.get("act"))

    pc = game.get("class")
    if pc is None:
        pc = header.get("class")
    al = game.get("ascension_level")
    if al is None:
        al = header.get("ascension_level")
    asc_int = 0
    if isinstance(al, (int, float)) and not isinstance(al, bool):
        try:
            asc_int = max(0, int(al))
        except (TypeError, ValueError, OverflowError):
            asc_int = 0

    summary: dict[str, Any] = {
        "state_id": state_id,
        "event_index": event_index,
        "screen_type": game.get("screen_type") or screen.get("type") or "NONE",
        "floor": floor,
        "act": act,
        "in_combat": in_combat,
        "turn_key": build_turn_key(vm),
        "current_hp": game.get("current_hp"),
        "max_hp": game.get("max_hp"),
        "gold": game.get("gold"),
        "class": pc,
        "ascension_level": asc_int,
    }

    if in_combat and isinstance(combat_vm, dict):
        player = combat_vm.get("player") or {}
        if isinstance(player, dict):
            summary["energy"] = player.get("energy")
            summary["player_block"] = combat_vm.get("player_block", player.get("block", 0))
        monsters_out: list[dict[str, Any]] = []
        for m in combat_vm.get("monsters") or []:
            if not isinstance(m, dict) or m.get("is_gone"):
                continue
            monsters_out.append(
                {
                    "name": m.get("name"),
                    "current_hp": m.get("current_hp"),
                    "max_hp": m.get("max_hp"),
                }
            )
        summary["monsters"] = monsters_out
        hand_out: list[dict[str, Any]] = []
        for c in combat_vm.get("hand") or []:
            if not isinstance(c, dict):
                continue
            hand_out.append(
                {
                    "name": c.get("name"),
                    "card_uuid_token": (c.get("card_uuid_token") or "")[:6] or None,
                }
            )
        summary["hand"] = hand_out

    actions = vm.get("actions") or []
    cmds = sorted(
        str(a.get("command", "") or "").strip()
        for a in actions
        if isinstance(a, dict) and str(a.get("command", "") or "").strip()
    )
    summary["legal_action_count"] = len(cmds)
    if cmds:
        joined = "\n".join(cmds)
        summary["legal_commands_fingerprint"] = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    deck = game.get("deck") if isinstance(game.get("deck"), list) else []
    relics = game.get("relics") if isinstance(game.get("relics"), list) else []
    summary["deck_size"] = len(deck)
    summary["relic_count"] = len(relics)

    stype = str(summary.get("screen_type") or "").upper()
    if stype == "GAME_OVER":
        summary["screen_name"] = game.get("screen_name")
        ss = game.get("screen_state") if isinstance(game.get("screen_state"), dict) else {}
        v = ss.get("victory")
        summary["victory"] = v if isinstance(v, bool) else False
        sc = ss.get("score", 0)
        try:
            summary["score"] = int(sc) if sc is not None else 0
        except (TypeError, ValueError):
            summary["score"] = 0

    return summary


def build_run_end_derived(game: dict[str, Any], *, state_id: str) -> dict[str, Any]:
    """Compact terminal-run fields for snapshot + run_metrics ``run_end`` row."""
    ss = game.get("screen_state") if isinstance(game.get("screen_state"), dict) else {}
    v = ss.get("victory")
    victory = v if isinstance(v, bool) else False
    sc = ss.get("score", 0)
    try:
        score = int(sc) if sc is not None else 0
    except (TypeError, ValueError):
        score = 0
    deck = game.get("deck") if isinstance(game.get("deck"), list) else []
    relics = game.get("relics") if isinstance(game.get("relics"), list) else []
    potions = game.get("potions") if isinstance(game.get("potions"), list) else []
    return {
        "state_id": state_id,
        "victory": victory,
        "score": score,
        "screen_name": game.get("screen_name"),
        "screen_type": game.get("screen_type"),
        "floor": game.get("floor"),
        "act": game.get("act"),
        "gold": game.get("gold"),
        "current_hp": game.get("current_hp"),
        "max_hp": game.get("max_hp"),
        "seed": game.get("seed"),
        "class": game.get("class"),
        "ascension_level": game.get("ascension_level"),
        "deck_size": len(deck),
        "relic_count": len(relics),
        "potion_slots": len(potions),
    }


def write_run_end_snapshot(run_dir: Path, raw_envelope: dict[str, Any], *, state_id: str) -> tuple[Path, dict[str, Any]]:
    """Write ``run_end_snapshot.json``: ``raw`` envelope first, full ``game_state`` copy, then ``derived``.

    Returns ``(path, derived)`` so callers can append matching ``run_end`` metrics.
    """
    recorded_at = utc_now_iso()
    raw_copy = copy.deepcopy(raw_envelope)
    inner = raw_envelope.get("state", raw_envelope)
    game = inner.get("game_state") if isinstance(inner, dict) else None
    game_copy = copy.deepcopy(game) if isinstance(game, dict) else {}
    derived = build_run_end_derived(game if isinstance(game, dict) else {}, state_id=state_id)
    derived["recorded_at"] = recorded_at
    payload: dict[str, Any] = {
        "recorded_at": recorded_at,
        "state_id": state_id,
        "raw": raw_copy,
        "game_state": game_copy,
        "derived": derived,
    }
    path = run_dir / RUN_END_SNAPSHOT_FILENAME
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    os.replace(tmp, path)
    return path, derived


def append_run_end_metric(run_dir: Path, *, state_id: str, derived: dict[str, Any]) -> None:
    """Append a compact ``type: run_end`` line to ``run_metrics.ndjson``."""
    rec: dict[str, Any] = {
        "type": "run_end",
        "state_id": state_id,
        "timestamp": utc_now_iso(),
        "snapshot_path": RUN_END_SNAPSHOT_FILENAME,
        "derived": dict(derived),
    }
    append_run_metric_line(run_dir, rec)


def append_run_metric_line(run_dir: Path, record: dict[str, Any]) -> None:
    """Append one JSON object to run_metrics.ndjson (append-only)."""
    path = run_dir / "run_metrics.ndjson"
    line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def append_state_run_metric(
    run_dir: Path,
    vm_summary: dict[str, Any],
    *,
    event_index: int,
    state_id: str,
) -> None:
    rec = {
        "type": "state",
        "event_index": event_index,
        "state_id": state_id,
        "timestamp": utc_now_iso(),
        "vm_summary": vm_summary,
    }
    append_run_metric_line(run_dir, rec)


def append_ai_decision_run_metric(run_dir: Path, trace: AgentTrace, state_log_path: Path) -> None:
    stem = state_log_path.stem
    try:
        event_index = int(stem)
    except ValueError:
        event_index = None
    val_err = (trace.validation.error if trace.validation else "") or ""
    err_body = (trace.error or "") or ""
    rec: dict[str, Any] = {
        "type": "ai_decision",
        "state_id": trace.state_id,
        "decision_id": trace.decision_id,
        "event_index": event_index,
        "timestamp": trace.timestamp or utc_now_iso(),
        "input_tokens": trace.token_usage.input_tokens,
        "output_tokens": trace.token_usage.output_tokens,
        "total_tokens": trace.token_usage.total_tokens,
        "cached_input_tokens": trace.token_usage.cached_input_tokens,
        "uncached_input_tokens": trace.token_usage.uncached_input_tokens,
        "latency_ms": trace.latency_ms,
        "status": trace.status,
        "validation_error": val_err[:500] if val_err else None,
        "error": err_body[:500] if err_body else None,
        "llm_model_used": trace.llm_model_used,
        "llm_turn_model_key": trace.llm_turn_model_key,
    }
    append_run_metric_line(run_dir, rec)


def write_ai_log(state_log_path: Path, trace: AgentTrace) -> None:
    payload = build_persisted_ai_log(trace)
    ai_log_path = build_ai_sidecar_path(state_log_path)
    with ai_log_path.open("w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, indent=2)
    append_ai_decision_run_metric(state_log_path.parent, trace, state_log_path)

