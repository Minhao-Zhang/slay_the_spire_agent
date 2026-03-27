from __future__ import annotations

from src.agent_core.tool_registry import (
    build_structured_tools,
    canonical_tool_name,
    execute_tool,
)


def test_canonical_tool_name_alias() -> None:
    assert canonical_tool_name("InspectDrawPileTool") == "inspect_draw_pile"


def test_execute_unknown_tool() -> None:
    out = execute_tool("not_a_tool", {}, {})
    assert "Unsupported" in out


def test_inspect_draw_pile_empty() -> None:
    vm = {"combat": {"draw_pile": []}}
    out = execute_tool("inspect_draw_pile", vm, {"question": "why"})
    assert "TOOL RESULT" in out
    assert "Inspect Draw Pile" in out


def test_inspect_draw_pile_lists_cards() -> None:
    vm = {
        "combat": {
            "draw_pile": [
                {
                    "name": "Defend",
                    "cost": 1,
                    "is_playable": True,
                    "kb": {"description": "Gain Block"},
                },
            ],
        },
    }
    out = execute_tool("inspect_draw_pile", vm, {"question": "order"})
    assert "Defend" in out
    assert "Block" in out


def test_inspect_deck_summary() -> None:
    vm = {
        "inventory": {
            "deck": [
                {"name": "Strike", "cost": 1, "type": "ATTACK", "upgrades": 0},
                {"name": "Strike", "cost": 1, "type": "ATTACK"},
            ],
        },
    }
    out = execute_tool("inspect_deck_summary", vm, {"question": "mix"})
    assert "deck_size=2" in out
    assert "ATTACK" in out


def test_build_structured_tools_invoke() -> None:
    vm = {"combat": {"draw_pile": []}, "inventory": {"deck": []}}
    tools = build_structured_tools(vm)
    assert len(tools) == 4
    draw = next(t for t in tools if t.name == "inspect_draw_pile")
    text = draw.invoke({"question": "x"})
    assert "TOOL RESULT" in text
