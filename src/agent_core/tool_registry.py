"""Tactical inspection tools (draw / discard / exhaust piles, deck summary).

Parity with legacy ``tool_registry`` behavior: formatted markdown sections for LLM consumption.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from langchain_core.tools import StructuredTool

ToolExecutor = Callable[[dict[str, Any], dict[str, Any]], str]


def _fmt_list(items: list[str], fallback: str = "None") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"


def _card_line(card: dict[str, Any], index: int) -> str:
    parts = [f"{index}. {card.get('name', '?')}"]
    if card.get("cost") is not None:
        parts.append(f"cost={card.get('cost')}")
    if card.get("upgrades", 0):
        parts.append(f"upgrades={card.get('upgrades')}")
    if card.get("has_target"):
        parts.append("targeted")
    if not card.get("is_playable", True):
        parts.append("unplayable")
    kb = card.get("kb") or {}
    if kb.get("description"):
        parts.append(f"desc={kb['description']}")
    return " | ".join(parts)


def format_pile_tool_result(tool_name: str, cards: list[dict[str, Any]]) -> str:
    lines = [_card_line(card, idx) for idx, card in enumerate(cards, start=1)]
    title = tool_name.replace("_", " ").title()
    return f"## TOOL RESULT: {title}\n{_fmt_list(lines)}"


def _pile_cards(vm: dict[str, Any], key: str) -> list[dict[str, Any]]:
    combat = vm.get("combat") or {}
    cards = combat.get(key) or []
    return cards if isinstance(cards, list) else []


def _run_pile_tool(
    vm: dict[str, Any],
    _arguments: dict[str, Any],
    pile_key: str,
    tool_name: str,
) -> str:
    cards = _pile_cards(vm, pile_key)
    return format_pile_tool_result(tool_name, cards)


def _run_deck_summary_tool(vm: dict[str, Any], _arguments: dict[str, Any]) -> str:
    inventory = vm.get("inventory") or {}
    deck = inventory.get("deck") or []
    if not isinstance(deck, list):
        deck = []

    type_counts: Counter[str] = Counter()
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
    type_lines = [
        f"{name}: {count}" for name, count in sorted(type_counts.items(), key=lambda x: x[0])
    ]
    summary_lines = [
        f"deck_size={len(deck)}",
        f"upgrades_total={upgrades}",
        f"avg_playable_cost={avg_cost:.2f}",
        "type_breakdown:",
        _fmt_list(type_lines),
    ]
    return "## TOOL RESULT: Inspect Deck Summary\n" + "\n".join(summary_lines)


_TOOL_SPECS: dict[str, dict[str, Any]] = {
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
        "description": (
            "Inspect deck-level aggregate stats (size, upgrades, type mix, average cost)."
        ),
        "executor": _run_deck_summary_tool,
    },
}

_TOOL_ALIASES: dict[str, str] = {
    "InspectDrawPileTool": "inspect_draw_pile",
    "InspectDiscardPileTool": "inspect_discard_pile",
    "InspectExhaustPileTool": "inspect_exhaust_pile",
}


def canonical_tool_name(name: str) -> str:
    return _TOOL_ALIASES.get(name, name)


def execute_tool(
    name: str,
    vm: dict[str, Any],
    arguments: dict[str, Any] | None = None,
) -> str:
    canonical = canonical_tool_name(name)
    spec = _TOOL_SPECS.get(canonical)
    if not spec:
        return "## TOOL RESULT: Unsupported Tool\n- This tool is not registered."
    executor: ToolExecutor = spec["executor"]
    return executor(vm, arguments or {})


def build_structured_tools(view_model: dict[str, Any]) -> list[StructuredTool]:
    """LangChain tools bound to this view-model snapshot (one graph step)."""

    def _wrap(name: str) -> StructuredTool:
        spec = _TOOL_SPECS[name]

        def _fn(question: str) -> str:
            return execute_tool(name, view_model, {"question": question})

        return StructuredTool.from_function(
            _fn,
            name=name,
            description=str(spec["description"]),
        )

    return [_wrap(n) for n in _TOOL_SPECS]
