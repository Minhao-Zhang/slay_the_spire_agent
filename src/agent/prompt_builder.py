from __future__ import annotations

from typing import Any


def _fmt_list(items: list[str], fallback: str = "None") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"


def _compact_text(text: str, *, limit: int = 160) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


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
    if kb.get("notes"):
        parts.append(f"notes={_compact_text(kb['notes'])}")
    if kb.get("ai"):
        parts.append(f"ai={_compact_text(kb['ai'])}")
    return " | ".join(parts)


def _relic_line(relic: dict[str, Any]) -> str:
    kb = relic.get("kb") or {}
    desc = kb.get("description", "")
    return f"{relic.get('name', '?')} | desc={desc}" if desc else relic.get("name", "?")


def _map_planning_lines(vm: dict[str, Any]) -> list[str]:
    screen = vm.get("screen") or {}
    if screen.get("type") != "MAP":
        return []

    map_state = vm.get("map") or {}
    lines: list[str] = []

    current_node = map_state.get("current_node")
    if current_node:
        lines.append(
            f"current_position=floor {vm.get('header', {}).get('floor', '?')} | "
            f"x={current_node.get('x', '?')} | y={current_node.get('y', '?')}"
        )
    else:
        lines.append("current_position=Selecting first node")

    next_nodes = map_state.get("next_nodes") or []
    if next_nodes:
        next_node_bits = [
            f"{node.get('symbol', '?')}@({node.get('x', '?')},{node.get('y', '?')})"
            for node in next_nodes
        ]
        lines.append("next_nodes=" + ", ".join(next_node_bits))

    lines.append(f"boss_available={bool(map_state.get('boss_available', False))}")

    boss_name = map_state.get("boss_name")
    if boss_name:
        boss_line = f"boss={boss_name}"
        boss_kb = map_state.get("boss_kb") or {}
        boss_notes: list[str] = []
        if boss_kb.get("notes"):
            boss_notes.append(f"notes={_compact_text(boss_kb['notes'], limit=120)}")
        if boss_kb.get("ai"):
            boss_notes.append(f"ai={_compact_text(boss_kb['ai'], limit=140)}")
        if boss_notes:
            boss_line += " | " + " | ".join(boss_notes)
        lines.append(boss_line)

    return lines


def _valid_play_lines(legal_actions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for action in legal_actions:
        command = str(action.get("command", "")).strip()
        if not command.startswith("PLAY "):
            continue
        lines.append(f"label={action.get('label', '?')} | command={command}")
    return lines


def build_user_prompt(vm: dict[str, Any], _state_id: str, recent_actions: list[str]) -> str:
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

    valid_play_lines = _valid_play_lines(legal_actions)
    map_lines = _map_planning_lines(vm)
    recent_action_lines = recent_actions[-5:]

    sections = [
        ("PLAYER STATE", _fmt_list(player_lines)),
        ("LEGAL ACTIONS", _fmt_list(legal_lines)),
        ("VALID PLAYS", _fmt_list(valid_play_lines, fallback="No playable cards.")),
        ("MONSTERS", _fmt_list(monster_lines)),
        ("HAND", _fmt_list(hand_lines)),
        ("PLAYER POWERS", _fmt_list(power_lines)),
        ("RELICS", _fmt_list(relic_lines)),
        ("POTIONS", _fmt_list(potion_lines)),
        ("CURRENT SCREEN", _fmt_list(screen_lines)),
        (
            "RECENT EXECUTED ACTIONS",
            _fmt_list(recent_action_lines, fallback="No prior executed actions in this scene."),
        ),
        (
            "TOOLING NOTES",
            "- Use a pile inspection tool only if you need hidden pile details.\n"
            "- Do not request a pile tool if the visible state already answers the question.",
        ),
    ]
    if map_lines:
        sections.insert(8, ("MAP PLANNING", _fmt_list(map_lines)))

    return "\n\n".join(f"## {title}\n{body}" for title, body in sections) + "\n"


def format_pile_tool_result(tool_name: str, cards: list[dict[str, Any]]) -> str:
    lines = [_card_line(card, idx) for idx, card in enumerate(cards, start=1)]
    title = tool_name.replace("_", " ").title()
    return f"## TOOL RESULT: {title}\n{_fmt_list(lines)}"

