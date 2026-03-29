"""Normalize view-model / ingress shapes that sometimes arrive as the wrong type."""

from __future__ import annotations

from typing import Any


def normalize_legal_actions(raw: Any) -> list[dict[str, Any]]:
    """Ensure ``vm['actions']`` is a list of dicts.

    Some ingress shapes may include bare command strings; code that does
    ``action.get(...)`` then raises ``'str' object has no attribute 'get'``.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str) and item.strip():
            s = item.strip()
            out.append({"label": s, "command": s, "style": "secondary"})
    return out


def prompt_command_for_action(action: dict[str, Any]) -> str:
    """Command string shown in LEGAL ACTIONS for the LLM.

    Card plays use ``PLAY <6-char token>`` / ``PLAY <token> <monster_index>`` when
    ``card_uuid_token`` is set; otherwise fall back to ``action[\"command\"]`` (e.g. numeric
    ``PLAY`` for the game bridge). Execution still uses the stored canonical command via
    ``resolve_token_play`` in policy.
    """
    cmd = str(action.get("command", "")).strip()
    if not cmd.upper().startswith("PLAY "):
        return cmd
    token = str(action.get("card_uuid_token") or "").strip().lower()
    if len(token) < 6:
        return cmd
    token = token[:6]
    if "monster_index" in action:
        try:
            mi = int(action["monster_index"])
        except (TypeError, ValueError):
            return cmd
        return f"PLAY {token} {mi}"
    return f"PLAY {token}"


def as_dict(obj: Any) -> dict[str, Any]:
    return obj if isinstance(obj, dict) else {}
