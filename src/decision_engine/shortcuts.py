"""Deterministic shortcuts (no LLM) for non-combat command screens.

Runs when the graph routes off ``in_fight`` (see overlay screens). Includes
combat-reward gold, confirm dialogs, single-action menus. Audit via ``shortcut_log``.
"""

from __future__ import annotations

import os
from typing import Any

# Screens where the game still sends ``combat_state`` but the player is not in turn-based combat
# (reward flows, map, shops, etc.). Shortcuts and queue drain must treat these as non-fight.
_OVERLAY_SCREENS_NOT_IN_FIGHT: frozenset[str] = frozenset(
    {
        "COMBAT_REWARD",
        "CARD_REWARD",
        "BOSS_REWARD",
        "MAP",
        "EVENT",
        "REST",
        "SHOP_ROOM",
        "SHOP_SCREEN",
        "CHEST",
        "GAME_OVER",
        "COMPLETE",
    },
)


def shortcuts_enabled() -> bool:
    raw = os.environ.get("SLAY_SHORTCUTS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def in_fight(view_model: dict[str, Any] | None) -> bool:
    """
    True during active combat turns.

    ``combat_state`` often remains populated on post-combat screens (e.g. COMBAT_REWARD);
    those must **not** count as in-fight so gold shortcuts and propose/auto lanes run.
    """
    if not view_model or view_model.get("combat") is None:
        return False
    screen = view_model.get("screen")
    if isinstance(screen, dict):
        st = str(screen.get("type") or "").strip().upper()
        if st in _OVERLAY_SCREENS_NOT_IN_FIGHT:
            return False
    return True


def choose_combat_reward_gold_command(vm: dict[str, Any]) -> str | None:
    screen = vm.get("screen") or {}
    if screen.get("type") != "COMBAT_REWARD":
        return None
    content = screen.get("content") or {}
    rewards = content.get("rewards") or []
    actions = vm.get("actions") or []
    for i, reward in enumerate(rewards):
        if str(reward.get("reward_type", "")).upper() != "GOLD":
            continue
        idx = reward.get("choice_index")
        if not isinstance(idx, int):
            idx = i
        command = f"choose {idx}"
        if any((a.get("command") or "").strip() == command for a in actions):
            return command
    return None


def _non_potion_commands(actions: list[dict[str, Any]]) -> set[str]:
    return {
        str(a.get("command") or "")
        for a in actions
        if not str(a.get("command") or "").upper().startswith("POTION")
    }


def try_deterministic_shortcut(
    ingress_raw: dict[str, Any],
    view_model: dict[str, Any],
) -> tuple[str | None, str]:
    """
    Return ``(command, kind)`` or ``("", "")`` if no shortcut.

    ``kind`` is one of: ``combat_reward_gold``, ``auto_confirm``, ``non_combat_potion``,
    ``single_action``.
    """
    if not ingress_raw.get("ready_for_command"):
        return None, ""
    actions_list = view_model.get("actions") or []
    if not actions_list:
        return None, ""

    gold = choose_combat_reward_gold_command(view_model)
    if gold:
        return gold, "combat_reward_gold"

    npc = _non_potion_commands(actions_list)
    if "CONFIRM" in npc and npc <= {"CONFIRM", "CANCEL"}:
        return "CONFIRM", "auto_confirm"

    if len(actions_list) == 1:
        sole = str(actions_list[0].get("command") or "").strip()
        if not sole:
            return None, ""
        if sole.upper().startswith("POTION"):
            return sole, "non_combat_potion"
        return sole, "single_action"

    return None, ""
