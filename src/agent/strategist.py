"""LLM strategist: knowledge selection + situation note + turn plan + strategy note updates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agent.config import AgentConfig
from src.agent.llm_client import LLMClient
from src.agent.memory.types import RetrievalHit
from src.agent.schemas import AgentTrace, TraceLlmCall, TraceTokenUsage
from src.agent.session_state import TurnConversation
from src.agent.vm_shapes import as_dict
from src.repo_paths import PACKAGE_ROOT

STRATEGIST_PROMPT_PATH = PACKAGE_ROOT / "agent" / "prompts" / "strategist_prompt.md"


def load_strategist_system_prompt() -> str:
    try:
        return STRATEGIST_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "You are the strategic planning layer for a Slay the Spire AI agent. "
            "Return JSON with selected_entry_ids, situation_note, turn_plan, strategy_update."
        )


def _deck_type_counts(vm: dict[str, Any]) -> dict[str, int]:
    inv = vm.get("inventory")
    inventory = inv if isinstance(inv, dict) else {}
    deck = inventory.get("deck") or []
    if not isinstance(deck, list):
        return {}
    type_counts: dict[str, int] = {}
    for card in deck:
        if not isinstance(card, dict):
            continue
        card_type = str((card.get("kb") or {}).get("type") or card.get("type") or "UNKNOWN").upper()
        type_counts[card_type] = type_counts.get(card_type, 0) + 1
    return type_counts


def build_game_state_for_strategist(vm: dict[str, Any]) -> dict[str, Any]:
    header = as_dict(vm.get("header"))
    screen = as_dict(vm.get("screen"))
    inv = as_dict(vm.get("inventory"))
    deck = inv.get("deck") if isinstance(inv.get("deck"), list) else []
    map_state = as_dict(vm.get("map"))
    combat = vm.get("combat") if isinstance(vm.get("combat"), dict) else None
    enemies: list[str] = []
    if combat:
        for m in combat.get("monsters") or []:
            if isinstance(m, dict) and not m.get("is_gone"):
                enemies.append(str(m.get("name", "")))

    relics_raw = inv.get("relics") or []
    relic_names: list[str] = []
    if isinstance(relics_raw, list):
        for r in relics_raw[:24]:
            if isinstance(r, dict):
                relic_names.append(str(r.get("name", "")))
            else:
                relic_names.append(str(r))

    potions_raw = inv.get("potions") or []
    potion_names: list[str] = []
    if isinstance(potions_raw, list):
        for p in potions_raw[:8]:
            if isinstance(p, dict):
                potion_names.append(str(p.get("name", "")))
            else:
                potion_names.append(str(p))

    cur_hp = header.get("current_hp")
    max_hp = header.get("max_hp")
    hp_str = f"{cur_hp}/{max_hp}" if cur_hp is not None and max_hp is not None else ""

    return {
        "floor": header.get("floor"),
        "act": header.get("act"),
        "screen": screen.get("type"),
        "class": header.get("class"),
        "hp": hp_str,
        "gold": header.get("gold"),
        "boss": map_state.get("boss_name"),
        "deck_size": len(deck),
        "deck_types": _deck_type_counts(vm),
        "relics": [x for x in relic_names if x],
        "potions": [x for x in potion_names if x],
        "enemies": enemies[:8],
    }


def parse_strategist_json(text: str) -> dict[str, Any] | None:
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


def hit_stable_id(hit: RetrievalHit) -> str:
    if hit.layer == "strategy":
        return f"strategy:{Path(hit.source_ref).name}"
    if hit.layer == "expert":
        return f"expert:{Path(hit.source_ref).name}"
    if hit.layer == "procedural":
        return f"procedural:{hit.source_ref}"
    return f"episodic:{hit.source_ref}"


def map_selected_ids_to_hits(
    pool_hits: list[RetrievalHit],
    selected_ids: list[str] | None,
    max_hits: int,
) -> list[RetrievalHit]:
    if not isinstance(selected_ids, list):
        return pool_hits[:max_hits]
    want = {str(x).strip() for x in selected_ids if str(x).strip()}
    by_id = {hit_stable_id(h): h for h in pool_hits}
    filtered = [by_id[i] for i in want if i in by_id]
    if not filtered:
        filtered = pool_hits[:max_hits]
    else:
        filtered = filtered[:max_hits]
    return filtered


def build_planning_block_from_strategist(situation_note: str, turn_plan: str) -> str | None:
    situation = situation_note.strip()
    plan = turn_plan.strip()
    if not situation and not plan:
        return None
    parts: list[str] = []
    if situation:
        parts.append(f"**Situation:** {situation}")
    if plan:
        parts.append(f"**Turn plan:** {plan}")
    return "## Strategic context\n" + "\n".join(parts)


def build_non_combat_plan_block(turn_plan: str) -> str | None:
    plan = turn_plan.strip()
    if not plan:
        return None
    return f"## TURN PLAN\n- {plan}\n"


@dataclass(slots=True)
class StrategistCallOutcome:
    hits: list[RetrievalHit]
    planning_context_block: str | None
    non_combat_plan_block: str | None
    strategy_update: dict[str, str]
    raw_parsed: dict[str, Any] | None


def run_strategist_llm(
    *,
    vm: dict[str, Any],
    trace: AgentTrace,
    session: TurnConversation,
    knowledge_index: list[dict[str, Any]],
    pool_hits: list[RetrievalHit],
    config: AgentConfig,
    llm: LLMClient,
    max_hits: int,
    emit_trace: Any,
) -> StrategistCallOutcome:
    system = load_strategist_system_prompt()
    prev = dict(session.strategy_notes)
    payload = {
        "game_state": build_game_state_for_strategist(vm),
        "knowledge_index": knowledge_index[:220],
        "previous_strategy": prev,
        "recent_actions": list(session.run_journal)[-12:],
    }
    user_msg = json.dumps(payload, ensure_ascii=False, default=str)
    trace.llm_calls.append(
        TraceLlmCall(
            round_index=len(trace.llm_calls) + 1,
            stage="strategist",
            input_messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        )
    )
    emit_trace()
    result = llm.generate_plain_completion(
        system_prompt=system,
        user_content=user_msg,
        llm_role="support",
        max_output_tokens=2048,
        reasoning_effort=None,
    )
    usage = result.get("token_usage")
    if isinstance(usage, TraceTokenUsage):
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "uncached_input_tokens",
        ):
            cur = getattr(trace.token_usage, name)
            new = getattr(usage, name, None)
            if new is not None:
                setattr(trace.token_usage, name, (cur or 0) + int(new))

    raw = str(result.get("raw_output") or "")
    data = parse_strategist_json(raw)
    if not data:
        return StrategistCallOutcome(
            hits=pool_hits[:max_hits],
            planning_context_block=None,
            non_combat_plan_block=None,
            strategy_update={},
            raw_parsed=None,
        )

    ids_raw = data.get("selected_entry_ids")
    selected = ids_raw if isinstance(ids_raw, list) else []
    hits = map_selected_ids_to_hits(pool_hits, selected, max_hits)

    situation = str(data.get("situation_note") or "").strip()
    turn_plan = str(data.get("turn_plan") or "").strip()
    planning_block = build_planning_block_from_strategist(situation, turn_plan)
    nc_block = build_non_combat_plan_block(turn_plan) if not vm.get("combat") else None

    su = data.get("strategy_update")
    strategy_update: dict[str, str] = {}
    if isinstance(su, dict):
        for key in ("deck_trajectory", "pathing_intent", "threat_assessment", "resource_plan"):
            val = su.get(key)
            if val is not None and str(val).strip():
                strategy_update[key] = str(val).strip()

    return StrategistCallOutcome(
        hits=hits,
        planning_context_block=planning_block,
        non_combat_plan_block=nc_block,
        strategy_update=strategy_update,
        raw_parsed=data,
    )
