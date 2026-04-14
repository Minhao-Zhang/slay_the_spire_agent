from __future__ import annotations

from typing import Any

from src.agent.session_state import format_executed_action
from src.agent.vm_shapes import as_dict

_SKIP_JOURNAL_COMMANDS = frozenset({"state", "wait", "wait 10", "start"})


def describe_execution(vm: dict[str, Any], action: str, legal_actions: list[dict[str, Any]]) -> str:
    """Return a human-readable journal line for a command about to be sent to the game."""
    cmd_norm = action.strip().lower()
    if cmd_norm in _SKIP_JOURNAL_COMMANDS:
        return ""

    screen = as_dict(vm.get("screen"))
    screen_type = str(screen.get("type") or "?").upper()
    formatted = format_executed_action(action, legal_actions)
    return f"[{screen_type}] {formatted}"
