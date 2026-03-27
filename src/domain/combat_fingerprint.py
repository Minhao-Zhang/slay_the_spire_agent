"""Stable combat encounter identity (legacy ``combat_encounter_fingerprint`` parity)."""

from __future__ import annotations

from typing import Any


def combat_encounter_fingerprint(view_model: dict[str, Any] | None) -> str | None:
    """Distinct fights on the same floor: floor plus live monsters (name + max_hp).

    Returns ``None`` when not in combat (no ``view_model["combat"]``).
    """
    if not view_model or not view_model.get("combat"):
        return None
    header = view_model.get("header") or {}
    floor = header.get("floor", "?")
    combat = view_model.get("combat") or {}
    if not isinstance(combat, dict):
        return None
    monsters = combat.get("monsters") or []
    parts: list[str] = []
    for m in monsters:
        if not isinstance(m, dict) or m.get("is_gone"):
            continue
        name = str(m.get("name", "?"))
        max_hp = m.get("max_hp", "?")
        parts.append(f"{name}:{max_hp}")
    parts.sort()
    if parts:
        return f"{floor}:" + "|".join(parts)
    return f"{floor}:empty"
