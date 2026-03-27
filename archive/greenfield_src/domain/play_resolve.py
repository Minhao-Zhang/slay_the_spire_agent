"""Resolve PLAY commands that use card UUID prefixes (``CARD_TOKEN_LEN`` chars)."""

from __future__ import annotations

import re
from typing import Any

from src.domain.card_token import CARD_TOKEN_LEN

_PLAY_TOKEN_RE = re.compile(
    rf"^PLAY\s+([A-Za-z0-9]{{{CARD_TOKEN_LEN}}})(?:\s+(\d+))?$",
    re.IGNORECASE,
)


def is_numeric_play(command: str) -> bool:
    """True if ``PLAY`` uses a small numeric hand index (mod canonical form)."""
    parts = command.strip().upper().split()
    return (
        len(parts) >= 2
        and parts[0] == "PLAY"
        and parts[1].isdigit()
        and len(parts[1]) <= 2
    )


def token_play_command_for_action(action: dict[str, Any]) -> str | None:
    """
    LLM-facing ``PLAY`` line using ``card_uuid_token`` (no numeric hand indices).

    Returns ``None`` for non-card actions.
    """
    tok = action.get("card_uuid_token")
    if not tok:
        return None
    cmd = str(action.get("command") or "")
    if not cmd.upper().startswith("PLAY "):
        return None
    t = str(tok).strip().lower()
    if "monster_index" in action and action.get("monster_index") is not None:
        return f"PLAY {t} {int(action['monster_index'])}"
    return f"PLAY {t}"


def _monster_index(action: dict[str, Any]) -> int | None:
    if "monster_index" not in action:
        return None
    v = action.get("monster_index")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def resolve_token_play(
    command: str,
    legal_actions: list[dict[str, Any]],
) -> str | None:
    """Map ``PLAY <token>`` or ``PLAY <token> <target>`` to canonical ``PLAY`` command."""
    m = _PLAY_TOKEN_RE.match(command.strip())
    if not m:
        return None
    token = m.group(1).lower()
    target_index = int(m.group(2)) if m.group(2) is not None else None

    matches: list[dict[str, Any]] = []
    for action in legal_actions:
        cmd = str(action.get("command", ""))
        if not cmd.upper().startswith("PLAY "):
            continue
        act_token = (action.get("card_uuid_token") or "").lower()
        if act_token != token:
            continue
        matches.append(action)

    if not matches:
        return None

    if target_index is not None:
        for action in matches:
            if _monster_index(action) == target_index:
                return str(action.get("command", "")).strip()
        return None

    # Omitted monster index (common LLM shape): accept single unambiguous row, or default target.
    non_targeted = [a for a in matches if _monster_index(a) is None]
    if len(non_targeted) == 1:
        return str(non_targeted[0].get("command", "")).strip()
    if len(non_targeted) > 1:
        return str(non_targeted[0].get("command", "")).strip()

    targeted = [a for a in matches if _monster_index(a) is not None]
    if len(targeted) == 1:
        return str(targeted[0].get("command", "")).strip()
    if len(targeted) > 1:
        targeted.sort(key=lambda a: (_monster_index(a) or 0, str(a.get("command", ""))))
        return str(targeted[0].get("command", "")).strip()

    return None


def resolve_play_with_token(
    command: str | None,
    legal_actions: list[dict[str, Any]],
) -> str | None:
    """If ``command`` is non-numeric ``PLAY``, try token resolution."""
    if not command:
        return None
    s = command.strip()
    if not s.upper().startswith("PLAY ") or is_numeric_play(s):
        return None
    return resolve_token_play(s, legal_actions)
