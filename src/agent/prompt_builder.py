from __future__ import annotations

from typing import Any


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


def _monster_line(monster: dict[str, Any], index: int) -> str:
    parts = [
        f"{index}. {monster.get('name', '?')}",
        f"hp={monster.get('hp_display', '?')}",
        f"intent={monster.get('intent_display', monster.get('intent', '?'))}",
    ]
    powers = monster.get("powers") or []
    if powers:
        parts.append(
            "powers=" + ", ".join(f"{p.get('name', '?')}({p.get('amount', '?')})" for p in powers)
        )
    kb = monster.get("kb") or {}
    if kb.get("moves"):
        parts.append("known_moves=" + ", ".join(kb["moves"][:3]))
    return " | ".join(parts)


def _relic_line(relic: dict[str, Any]) -> str:
    kb = relic.get("kb") or {}
    desc = kb.get("description", "")
    return f"{relic.get('name', '?')} | desc={desc}" if desc else relic.get("name", "?")


def build_user_prompt(vm: dict[str, Any], state_id: str, recent_actions: list[str]) -> str:
    header = vm.get("header") or {}
    inventory = vm.get("inventory") or {}
    combat = vm.get("combat") or {}
    screen = vm.get("screen") or {}
    legal_actions = vm.get("actions") or []

    player_lines = [
        f"class={header.get('class', '?')}",
        f"floor={header.get('floor', '?')}",
        f"hp={header.get('hp_display', '?')}",
        f"gold={header.get('gold', '?')}",
        f"energy={header.get('energy', '?')}",
        f"turn={header.get('turn', '?')}",
    ]
    if combat:
        player_lines.append(f"block={combat.get('player_block', 0)}")

    relic_lines = [_relic_line(r) for r in inventory.get("relics", [])]
    potion_lines = []
    for idx, potion in enumerate(inventory.get("potions", []), start=1):
        effect = ((potion.get("kb") or {}).get("effect")) or ""
        line = f"{idx}. {potion.get('name', '?')}"
        if effect:
            line += f" | effect={effect}"
        potion_lines.append(line)

    hand_lines = [_card_line(card, idx) for idx, card in enumerate(combat.get("hand", []), start=1)]
    monster_lines = [
        _monster_line(monster, idx)
        for idx, monster in enumerate(combat.get("monsters", []), start=1)
        if not monster.get("is_gone")
    ]
    power_lines = [
        f"{power.get('name', '?')}({power.get('amount', '?')})"
        for power in combat.get("player_powers", [])
    ]

    screen_lines = [f"type={screen.get('type', 'NONE')}"]
    if screen.get("title"):
        screen_lines.append(f"title={screen.get('title')}")
    if screen.get("content"):
        screen_lines.append(f"content_keys={', '.join(screen['content'].keys())}")

    legal_lines = [
        f"{idx}. label={action.get('label', '?')} | command={action.get('command', '?')}"
        for idx, action in enumerate(legal_actions, start=1)
    ]

    recent_action_lines = recent_actions[-5:]

    return (
        "## STATE ID\n"
        f"{state_id}\n\n"
        "## PLAYER STATE\n"
        f"{_fmt_list(player_lines)}\n\n"
        "## PLAYER POWERS\n"
        f"{_fmt_list(power_lines)}\n\n"
        "## RELICS\n"
        f"{_fmt_list(relic_lines)}\n\n"
        "## POTIONS\n"
        f"{_fmt_list(potion_lines)}\n\n"
        "## MONSTERS\n"
        f"{_fmt_list(monster_lines)}\n\n"
        "## HAND\n"
        f"{_fmt_list(hand_lines)}\n\n"
        "## CURRENT SCREEN\n"
        f"{_fmt_list(screen_lines)}\n\n"
        "## LEGAL ACTIONS\n"
        f"{_fmt_list(legal_lines)}\n\n"
        "## RECENT ACTIONS THIS TURN\n"
        f"{_fmt_list(recent_action_lines, fallback='No prior actions this turn.')}\n\n"
        "## TOOLING NOTES\n"
        "- Use a pile inspection tool only if you need hidden pile details.\n"
        "- Do not request a pile tool if the visible state already answers the question.\n"
    )


def format_pile_tool_result(tool_name: str, cards: list[dict[str, Any]]) -> str:
    lines = [_card_line(card, idx) for idx, card in enumerate(cards, start=1)]
    title = tool_name.replace("_", " ").title()
    return f"## TOOL RESULT: {title}\n{_fmt_list(lines)}"

