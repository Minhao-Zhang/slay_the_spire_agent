from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from src.agent.prompt_builder import format_pile_tool_result


ToolExecutor = Callable[[dict[str, Any], dict[str, Any]], str]


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


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "inspect_draw_pile": {
        "description": "Inspect hidden draw pile details to support this turn's decision.",
        "executor": lambda vm, arguments: _run_pile_tool(
            vm, arguments, "draw_pile", "inspect_draw_pile"
        ),
    },
    "inspect_discard_pile": {
        "description": "Inspect discard pile composition for near-future planning.",
        "executor": lambda vm, arguments: _run_pile_tool(
            vm, arguments, "discard_pile", "inspect_discard_pile"
        ),
    },
    "inspect_exhaust_pile": {
        "description": "Inspect exhaust pile to reason about remaining scaling and key cards.",
        "executor": lambda vm, arguments: _run_pile_tool(
            vm, arguments, "exhaust_pile", "inspect_exhaust_pile"
        ),
    },
    "inspect_deck_summary": {
        "description": "Inspect deck-level aggregate stats (size, upgrades, type mix, average cost).",
        "executor": _run_deck_summary_tool,
    },
}

TOOL_ALIASES: dict[str, str] = {
    "InspectDrawPileTool": "inspect_draw_pile",
    "InspectDiscardPileTool": "inspect_discard_pile",
    "InspectExhaustPileTool": "inspect_exhaust_pile",
}


def canonical_tool_name(name: str) -> str:
    return TOOL_ALIASES.get(name, name)


def list_function_tools() -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name, spec in TOOL_SPECS.items():
        tools.append(
            {
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
                "strict": True,
            }
        )
    return tools


def execute_tool(name: str, vm: dict[str, Any], arguments: dict[str, Any] | None = None) -> str:
    canonical = canonical_tool_name(name)
    spec = TOOL_SPECS.get(canonical)
    if not spec:
        return "## TOOL RESULT: Unsupported Tool\n- This tool is not registered."
    executor: ToolExecutor = spec["executor"]
    return executor(vm, arguments or {})

