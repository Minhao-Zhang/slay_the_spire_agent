"""Shared deterministic reductions for :class:`RunReport` (file or SQL-backed)."""

from __future__ import annotations

from typing import Any

from src.agent.reflection.report_types import DecisionRecord

_SAMPLE_FLOORS = frozenset({1, 6, 12, 17, 25, 33, 40, 50})
_COMBAT_KEYWORDS = (
    "boss",
    "heart",
    "donu",
    "deca",
    "elite",
    "champ",
    "collector",
    "automaton",
    "guardian",
    "awakened",
)


def decision_record_from_ai_dict(data: dict[str, Any], *, source_path: str = "") -> DecisionRecord:
    """Build :class:`DecisionRecord` from a persisted ``*.ai.json`` payload."""
    tools = data.get("tool_names")
    if not isinstance(tools, list):
        tools = []
    lr = data.get("lessons_retrieved", 0)
    if not isinstance(lr, int):
        try:
            lr = int(lr)
        except (TypeError, ValueError):
            lr = 0
    sr = data.get("strategist_ran")
    strategist_ran = bool(sr) if isinstance(sr, bool) else str(sr).lower() == "true"
    return DecisionRecord(
        state_id=str(data.get("state_id") or ""),
        turn_key=str(data.get("turn_key") or ""),
        status=str(data.get("status") or ""),
        final_decision=data.get("final_decision") if data.get("final_decision") is not None else None,
        planner_summary=str(data.get("planner_summary") or ""),
        llm_model_used=str(data.get("llm_model_used") or ""),
        reasoning_effort_used=str(data.get("reasoning_effort_used") or ""),
        strategist_ran=strategist_ran,
        lessons_retrieved=lr,
        tool_names=[str(t) for t in tools if t],
        source_path=source_path,
    )


def is_key_combat_context(turn_key: str, planner_summary: str) -> bool:
    blob = f"{turn_key} {planner_summary}".lower()
    return any(k in blob for k in _COMBAT_KEYWORDS) or "combat" in blob


def reduce_path_deck_resources(
    vm_summaries: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build ``path_summary``, ``deck_changes``, ``resource_snapshots`` from ordered vm summaries."""
    path_summary: list[str] = []
    deck_changes: list[dict[str, Any]] = []
    resource_snapshots: list[dict[str, Any]] = []
    prev_deck: int | None = None
    prev_screen = ""
    seen_floors_sample: set[int] = set()

    for vm_s in vm_summaries:
        floor = vm_s.get("floor")
        fl_int: int | None
        try:
            fl_int = int(floor) if floor is not None else None
        except (TypeError, ValueError):
            fl_int = None
        stype = str(vm_s.get("screen_type") or "NONE").upper()
        if fl_int is not None:
            path_summary.append(f"floor {fl_int} {stype}")
            if fl_int in _SAMPLE_FLOORS and fl_int not in seen_floors_sample:
                seen_floors_sample.add(fl_int)
                resource_snapshots.append(
                    {
                        "floor": fl_int,
                        "hp": vm_s.get("current_hp"),
                        "max_hp": vm_s.get("max_hp"),
                        "gold": vm_s.get("gold"),
                        "deck_size": vm_s.get("deck_size"),
                        "relic_count": vm_s.get("relic_count"),
                    }
                )
        ds = vm_s.get("deck_size")
        try:
            ds_int = int(ds) if ds is not None else None
        except (TypeError, ValueError):
            ds_int = None
        if prev_deck is not None and ds_int is not None and ds_int != prev_deck:
            action = "deck_size_change"
            if stype == "COMBAT_REWARD" or prev_screen == "COMBAT_REWARD":
                action = "possible_card_pick"
            deck_changes.append(
                {
                    "floor": fl_int,
                    "action": action,
                    "from": prev_deck,
                    "to": ds_int,
                    "screen": stype,
                }
            )
        if ds_int is not None:
            prev_deck = ds_int
        prev_screen = stype

    if len(path_summary) > 80:
        path_summary = (
            path_summary[:40] + [f"... ({len(path_summary) - 80} more) ..."] + path_summary[-40:]
        )

    return path_summary, deck_changes, resource_snapshots
