from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from src.agent.prompt_builder import format_pile_tool_result


ToolExecutor = Callable[[dict[str, Any], dict[str, Any]], str]


def tool_filter_for_context(vm: dict[str, Any]) -> str | None:
    """Return a tool context filter string based on the current screen."""
    if vm.get("combat"):
        return "combat"
    screen_type = str((vm.get("screen") or {}).get("type", "NONE")).upper()
    return {
        "MAP": "map",
        "CARD_REWARD": "reward",
        "COMBAT_REWARD": "reward",
        "SHOP_SCREEN": "reward",
        "SHOP_ROOM": "reward",
        "BOSS_REWARD": "reward",
        "EVENT": "event",
        "REST": "reward",
    }.get(screen_type)


def _fmt_list(items: list[str], fallback: str = "None") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"


def _pile_cards(vm: dict[str, Any], key: str) -> list[dict[str, Any]]:
    combat = vm.get("combat") or {}
    cards = combat.get(key) or []
    return cards if isinstance(cards, list) else []


def _run_pile_tool(vm: dict[str, Any], _arguments: dict[str, Any], pile_key: str, tool_name: str) -> str:
    cards = _pile_cards(vm, pile_key)
    return format_pile_tool_result(tool_name, cards)


def _run_deck_summary_tool(vm: dict[str, Any], _arguments: dict[str, Any]) -> str:
    inventory = vm.get("inventory") or {}
    deck = inventory.get("deck") or []
    if not isinstance(deck, list):
        deck = []

    type_counts: Counter = Counter()
    playable_costs: list[int] = []
    upgrades = 0
    for card in deck:
        if not isinstance(card, dict):
            continue
        card_type = (
            (card.get("kb") or {}).get("type")
            or card.get("type")
            or "UNKNOWN"
        )
        type_counts[str(card_type).upper()] += 1
        cost = card.get("cost")
        if isinstance(cost, int) and cost >= 0:
            playable_costs.append(cost)
        upgrades += int(card.get("upgrades", 0) or 0)

    avg_cost = (sum(playable_costs) / len(playable_costs)) if playable_costs else 0.0
    type_lines = [f"{name}: {count}" for name, count in sorted(type_counts.items(), key=lambda x: x[0])]
    summary_lines = [
        f"deck_size={len(deck)}",
        f"upgrades_total={upgrades}",
        f"avg_playable_cost={avg_cost:.2f}",
        "type_breakdown:",
        _fmt_list(type_lines),
    ]
    return "## TOOL RESULT: Inspect Deck Summary\n" + "\n".join(summary_lines)


_FULL_DECK_DESC_MAX = 220


def _run_full_deck_tool(vm: dict[str, Any], _arguments: dict[str, Any]) -> str:
    inventory = vm.get("inventory") or {}
    deck = inventory.get("deck") or []
    if not isinstance(deck, list):
        deck = []

    lines: list[str] = [f"deck_size={len(deck)}", ""]
    for i, card in enumerate(deck, start=1):
        if not isinstance(card, dict):
            lines.append(f"{i}. (invalid entry)")
            continue
        name = card.get("name", "?")
        kb = card.get("kb") or {}
        ctype = kb.get("type") or card.get("type") or "?"
        cost = card.get("cost", "?")
        up = int(card.get("upgrades", 0) or 0)
        desc = str(kb.get("description") or "").replace("\n", " ").strip()
        if len(desc) > _FULL_DECK_DESC_MAX:
            desc = desc[: _FULL_DECK_DESC_MAX - 1] + "…"
        lines.append(f"{i}. {name} | type={ctype} | cost={cost} | upgrades={up}")
        if desc:
            lines.append(f"   desc={desc}")
    return "## TOOL RESULT: Inspect Full Deck\n" + "\n".join(lines)


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "inspect_draw_pile": {
        "description": "Inspect hidden draw pile details to support this turn's decision.",
        "contexts": ["combat"],
        "executor": lambda vm, arguments: _run_pile_tool(
            vm, arguments, "draw_pile", "inspect_draw_pile"
        ),
    },
    "inspect_discard_pile": {
        "description": "Inspect discard pile composition for near-future planning.",
        "contexts": ["combat"],
        "executor": lambda vm, arguments: _run_pile_tool(
            vm, arguments, "discard_pile", "inspect_discard_pile"
        ),
    },
    "inspect_exhaust_pile": {
        "description": "Inspect exhaust pile to reason about remaining scaling and key cards.",
        "contexts": ["combat"],
        "executor": lambda vm, arguments: _run_pile_tool(
            vm, arguments, "exhaust_pile", "inspect_exhaust_pile"
        ),
    },
    "inspect_deck_summary": {
        "description": "Inspect deck-level aggregate stats (size, upgrades, type mix, average cost).",
        "contexts": ["combat", "reward", "shop", "event", "map"],
        "executor": _run_deck_summary_tool,
    },
    "inspect_full_deck": {
        "description": (
            "List every card in the master deck with name, type, cost, upgrades, and KB description."
        ),
        "contexts": ["combat", "map", "reward", "event", "shop", "rest"],
        "executor": _run_full_deck_tool,
    },
}

TOOL_ALIASES: dict[str, str] = {
    "InspectDrawPileTool": "inspect_draw_pile",
    "InspectDiscardPileTool": "inspect_discard_pile",
    "InspectExhaustPileTool": "inspect_exhaust_pile",
}


def canonical_tool_name(name: str) -> str:
    return TOOL_ALIASES.get(name, name)


def _function_tool_schema(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": spec["description"],
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Why this tool is needed for the current decision.",
                }
            },
            "required": ["question"],
            "additionalProperties": False,
        },
        "strict": False,
    }


def list_function_tools() -> list[dict[str, Any]]:
    return [_function_tool_schema(name, spec) for name, spec in TOOL_SPECS.items()]


def list_function_tools_for_context(tool_filter: str | None) -> list[dict[str, Any]]:
    """Return OpenAI function tool dicts matching ``tool_filter`` (``None`` = all tools)."""
    if tool_filter is None:
        return list_function_tools()
    out: list[dict[str, Any]] = []
    for name, spec in TOOL_SPECS.items():
        ctx = spec.get("contexts") or []
        if "any" in ctx or tool_filter in ctx:
            out.append(_function_tool_schema(name, spec))
    return out


def execute_tool(name: str, vm: dict[str, Any], arguments: dict[str, Any] | None = None) -> str:
    canonical = canonical_tool_name(name)
    spec = TOOL_SPECS.get(canonical)
    if not spec:
        return "## TOOL RESULT: Unsupported Tool\n- This tool is not registered."
    executor: ToolExecutor = spec["executor"]
    return executor(vm, arguments or {})

