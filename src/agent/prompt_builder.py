from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Lazy-loaded map of buff/power name -> description (from buff_descriptions.json + powers)
_BUFF_DESCRIPTIONS: dict[str, str] | None = None
_TOKEN_PATTERN = re.compile(r"\[([^\]]+)\]")


def _get_buff_descriptions() -> dict[str, str]:
    """Load buff_descriptions.json and merge with get_power_info for any missing names."""
    global _BUFF_DESCRIPTIONS
    if _BUFF_DESCRIPTIONS is not None:
        return _BUFF_DESCRIPTIONS
    base = Path(__file__).resolve().parent.parent.parent
    path = base / "data" / "processed" / "buff_descriptions.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            _BUFF_DESCRIPTIONS = json.load(f)
    else:
        _BUFF_DESCRIPTIONS = {}
    # Backfill from knowledge_base for names we might see (e.g. "Draw Card", "Energized")
    try:
        from src.reference.knowledge_base import get_power_info
        for name in list(_BUFF_DESCRIPTIONS):
            pass  # already have
        # We don't preload all powers; we resolve on demand in _buff_glossary_lines
    except Exception:
        pass
    return _BUFF_DESCRIPTIONS


def _resolve_buff_description(name: str) -> str:
    """Get description for a power/buff name. Uses buff_descriptions.json then get_power_info."""
    name = (name or "").strip()
    if not name:
        return ""
    descs = _get_buff_descriptions()
    if name in descs:
        return descs[name]
    try:
        from src.reference.knowledge_base import get_power_info
        info = get_power_info(name)
        if info and info.get("effect"):
            return info["effect"]
    except Exception:
        pass
    return ""


def _extract_tokens_from_text(text: str | None) -> set[str]:
    """Extract [Token] names from description/effect text."""
    if not text:
        return set()
    return set(_TOKEN_PATTERN.findall(text))


def _fmt_list(items: list[str], fallback: str = "None") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"


def _compact_text(text: str, *, limit: int = 160) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _card_line(card: dict[str, Any], index: int, show_token: bool = False) -> str:
    parts = [f"{index}. {card.get('name', '?')}"]
    if card.get("cost") is not None:
        parts.append(f"cost={card.get('cost')}")
    if card.get("upgrades", 0):
        parts.append(f"upgrades={card.get('upgrades')}")
    if card.get("has_target"):
        parts.append("targeted")
    if not card.get("is_playable", True):
        parts.append("unplayable")
    if show_token:
        uuid_full = card.get("uuid", "")
        token = uuid_full[:6] if uuid_full else ""
        if token:
            parts.append(f"token={token}")
    kb = card.get("kb") or {}
    if kb.get("description"):
        parts.append(f"desc={kb['description']}")
    return " | ".join(parts)


def _power_line(power: dict[str, Any]) -> str:
    """Format a single power with name, amount, and effect description for the prompt."""
    name = power.get("name", "?")
    amount = power.get("amount", "?")
    kb = power.get("kb") or {}
    effect = kb.get("effect", "")
    if effect:
        return f"{name}({amount}) | effect={_compact_text(effect, limit=120)}"
    return f"{name}({amount})"


def _monster_line(monster: dict[str, Any], index: int) -> str:
    parts = [
        f"{index}. {monster.get('name', '?')}",
        f"hp={monster.get('hp_display', '?')}",
        f"block={monster.get('block', 0)}",
        f"intent={monster.get('intent_display', monster.get('intent', '?'))}",
    ]
    powers = monster.get("powers") or []
    if powers:
        power_parts = []
        for p in powers:
            line = _power_line(p)
            power_parts.append(line)
        parts.append("powers=" + "; ".join(power_parts))
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


def _buff_glossary_lines(vm: dict[str, Any]) -> list[str]:
    """Collect all buff/power names present in this state (player, monsters, relic/potion text)
    and return lines 'Name: effect' for the prompt. Ensures the model has descriptions for every
    power/buff that appears."""
    seen: set[str] = set()
    lines: list[str] = []

    def add(name: str) -> None:
        if not name or name in seen:
            return
        seen.add(name)
        desc = _resolve_buff_description(name)
        if desc:
            lines.append(f"{name}: {_compact_text(desc, limit=140)}")

    # Player powers
    for p in (vm.get("combat") or {}).get("player_powers", []):
        add((p.get("name") or "").strip())

    # Monster powers
    for m in (vm.get("combat") or {}).get("monsters", []):
        if m.get("is_gone"):
            continue
        for p in m.get("powers") or []:
            add((p.get("name") or "").strip())

    # Tokens in relic descriptions
    for r in (vm.get("inventory") or {}).get("relics", []):
        kb = r.get("kb") or {}
        for token in _extract_tokens_from_text(kb.get("description")):
            add(token.strip())

    # Tokens in potion effects
    for p in (vm.get("inventory") or {}).get("potions", []):
        kb = p.get("kb") or {}
        for token in _extract_tokens_from_text(kb.get("effect")):
            add(token.strip())
        for token in _extract_tokens_from_text(p.get("effect_sacred_bark")):
            add(token.strip())

    return sorted(lines)  # deterministic order


def _map_planning_lines(vm: dict[str, Any]) -> list[str]:
    screen = vm.get("screen") or {}
    if screen.get("type") != "MAP":
        return []

    map_state = vm.get("map") or {}
    lines: list[str] = [
        "Path choice is crucial for run success; choose deliberately (consider elites, rest, shops, events).",
    ]

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


def _map_2d_grid_lines(map_state: dict[str, Any]) -> list[str]:
    """Build a 2D ASCII grid of the map for spatial layout. Uses * for current node."""
    nodes = map_state.get("nodes") or []
    if not nodes:
        return []

    xs = [n.get("x") for n in nodes if n.get("x") is not None]
    ys = [n.get("y") for n in nodes if n.get("y") is not None]
    if not xs or not ys:
        return []

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    h = max_y - min_y + 1
    w = max_x - min_x + 1
    grid: list[list[str]] = [[" " for _ in range(w)] for _ in range(h)]

    for n in nodes:
        x, y = n.get("x"), n.get("y")
        if x is None or y is None:
            continue
        sy = y - min_y
        sx = x - min_x
        if 0 <= sy < h and 0 <= sx < w:
            sym = n.get("symbol", "?")
            grid[sy][sx] = str(sym)[0] if sym else "?"

    current_node = map_state.get("current_node")
    if current_node is not None:
        cx = current_node.get("x")
        cy = current_node.get("y")
        if cx is not None and cy is not None and min_x <= cx <= max_x and min_y <= cy <= max_y:
            grid[cy - min_y][cx - min_x] = "*"

    lines = [
        "Symbols: M=monster E=elite R=rest $=shop ?=unknown T=treasure; * = you.",
        "2D view (y increases downward):",
    ]
    for row in grid:
        lines.append("  " + " ".join(row))
    return lines


def _map_scene_lines(vm: dict[str, Any]) -> list[str]:
    """Build a text map scene (layout, connections, current, next choices) for path selection."""
    screen = vm.get("screen") or {}
    if screen.get("type") != "MAP":
        return []

    map_state = vm.get("map") or {}
    nodes = map_state.get("nodes") or []
    current_node = map_state.get("current_node")
    next_nodes = map_state.get("next_nodes") or []
    boss_available = bool(map_state.get("boss_available", False))

    lines: list[str] = []

    grid_lines = _map_2d_grid_lines(map_state)
    if grid_lines:
        lines.extend(grid_lines)

    if nodes:
        by_y: dict[int, list[dict[str, Any]]] = {}
        for n in nodes:
            y = n.get("y", 0)
            by_y.setdefault(y, []).append(n)
        layout_parts = []
        for y in sorted(by_y):
            row = sorted(by_y[y], key=lambda n: (n.get("x", 0), n.get("y", 0)))
            cells = [f"({n.get('x','?')},{n.get('y','?')})={n.get('symbol','?')}" for n in row]
            layout_parts.append(f"y={y}: " + " ".join(cells))
        lines.append("layout: " + " | ".join(layout_parts))

        connections: list[str] = []
        for n in nodes:
            x, y = n.get("x"), n.get("y")
            for c in (n.get("children") or []):
                cx, cy = c.get("x"), c.get("y")
                connections.append(f"({x},{y})->({cx},{cy})")
        if connections:
            lines.append("connections: " + ", ".join(connections))

    if current_node is not None:
        x, y = current_node.get("x", "?"), current_node.get("y", "?")
        sym = current_node.get("symbol", "?")
        lines.append(f"you_are_here: ({x},{y}) [{sym}]")
    else:
        lines.append("you_are_here: Selecting first node")

    if next_nodes:
        choice_parts = [
            f"{i}. ({n.get('x','?')},{n.get('y','?')})={n.get('symbol','?')} -> choose {i}"
            for i, n in enumerate(next_nodes)
        ]
        lines.append("next_choices: " + " | ".join(choice_parts))
    if boss_available:
        lines.append("boss: available -> choose boss")

    return lines


def _screen_content_lines(vm: dict[str, Any]) -> list[str]:
    """Render the current non-combat screen content into human-readable lines for the LLM prompt.

    Returns an empty list when in combat (combat state already has its own sections)
    or when there is nothing meaningful to show.
    """
    if vm.get("combat"):
        return []

    screen = vm.get("screen") or {}
    screen_type = screen.get("type", "NONE")
    content = screen.get("content") or {}
    lines: list[str] = []

    if screen_type in ("GRID", "HAND_SELECT"):
        purpose = content.get("grid_purpose", "")
        num = content.get("num_cards", 1)
        cards = content.get("cards") or []
        if purpose:
            lines.append(f"Action: {purpose} {num} card(s) from the list below.")
        else:
            lines.append(f"Select {num} card(s) from the list below.")
        for i, card in enumerate(cards):
            lines.append(_card_line(card, i, show_token=False))

    elif screen_type == "CARD_REWARD":
        cards = content.get("cards") or []
        lines.append("Choose one card to add to your deck (or skip):")
        for i, card in enumerate(cards):
            lines.append(_card_line(card, i, show_token=False))

    elif screen_type == "COMBAT_REWARD":
        rewards = content.get("rewards") or []
        lines.append("Combat rewards — choose one or skip:")
        for r in rewards:
            label = r.get("label", r.get("reward_type", "?"))
            idx = r.get("choice_index", "?")
            relic_kb = r.get("relic_kb") or {}
            desc = relic_kb.get("description", "")
            line = f"{idx}. {label}"
            if desc:
                line += f" | {_compact_text(desc, limit=120)}"
            lines.append(line)

    elif screen_type == "EVENT":
        body = _compact_text(content.get("body_text", ""), limit=400)
        if body:
            lines.append(f"Event text: {body}")
        event_kb = content.get("event_kb") or {}
        kb_choices = event_kb.get("choices") or []
        for i, opt in enumerate(content.get("options") or []):
            label = opt.get("label", f"Option {i}")
            text = _compact_text(opt.get("text", ""), limit=160)
            disabled = opt.get("disabled", False)
            kb_choice = kb_choices[i] if i < len(kb_choices) else {}
            outcome = _compact_text(kb_choice.get("outcome", ""), limit=120) if kb_choice else ""
            line = f"{i}. {label}"
            if text:
                line += f" — {text}"
            if outcome:
                line += f" [outcome: {outcome}]"
            if disabled:
                line += " (disabled)"
            lines.append(line)

    elif screen_type == "REST":
        lines.append("Rest site options:")
        for opt in content.get("rest_options") or []:
            lbl = opt.get("label", "?")
            desc = opt.get("description", "")
            lines.append(f"- {lbl}: {desc}" if desc else f"- {lbl}")
        if content.get("has_rested"):
            lines.append("(Already rested this stop.)")

    elif screen_type == "SHOP_SCREEN":
        gold = content.get("gold", 0)
        lines.append(f"Shop — you have {gold} gold.")
        shop_cards = content.get("shop_cards") or []
        if shop_cards:
            lines.append("Cards for sale:")
            for card in shop_cards:
                price = card.get("price", "?")
                lines.append(f"  {_card_line(card, card.get('choice_index', '?'), show_token=False)} | price={price}g")
        shop_relics = content.get("shop_relics") or []
        if shop_relics:
            lines.append("Relics for sale:")
            for r in shop_relics:
                price = r.get("price", "?")
                kb = r.get("kb") or {}
                desc = _compact_text(kb.get("description", ""), limit=120)
                idx = r.get("choice_index", "?")
                line = f"  {idx}. {r.get('name', '?')} | price={price}g"
                if desc:
                    line += f" | {desc}"
                lines.append(line)
        shop_potions = content.get("shop_potions") or []
        if shop_potions:
            lines.append("Potions for sale:")
            for p in shop_potions:
                price = p.get("price", "?")
                kb = p.get("kb") or {}
                effect = _compact_text(kb.get("effect", ""), limit=100)
                idx = p.get("choice_index", "?")
                line = f"  {idx}. {p.get('name', '?')} | price={price}g"
                if effect:
                    line += f" | {effect}"
                lines.append(line)
        if content.get("purge_available"):
            lines.append(f"Card removal available | cost={content.get('purge_cost', '?')}g")

    elif screen_type == "BOSS_REWARD":
        relics = content.get("relics") or []
        lines.append("Choose one boss relic:")
        for i, r in enumerate(relics):
            kb = r.get("kb") or {}
            desc = _compact_text(kb.get("description", ""), limit=120)
            line = f"{i}. {r.get('name', '?')}"
            if desc:
                line += f" | {desc}"
            lines.append(line)

    elif screen_type == "CHEST":
        lines.append(f"Treasure chest: {content.get('chest_type', 'Unknown')}")
        if content.get("chest_open"):
            lines.append("(Chest already opened.)")

    elif screen_type == "GAME_OVER":
        victory = content.get("victory", False)
        score = content.get("score", 0)
        lines.append(f"{'Victory' if victory else 'Defeat'} — score: {score}")

    return lines


def _valid_play_lines(legal_actions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for action in legal_actions:
        command = str(action.get("command", "")).strip()
        if not command.startswith("PLAY "):
            continue
        lines.append(f"label={action.get('label', '?')} | command={command}")
    return lines


# Guidance injected into the user prompt when making card/combat decisions.
CARD_CHOICE_GUIDANCE = [
    "Maximize damage long term and minimize health loss long term.",
    "Plan ahead: consider next turn, remaining enemies, and what you might draw.",
    "Do damage calculations when choosing attacks and targets (enemy block, Vulnerable, Weak, multi-hit).",
    "Prefer lines that kill or heavily weaken the most dangerous enemy when possible.",
    "Use block and debuffs when they prevent more damage than alternative plays.",
]

COMBAT_PLAN_SYSTEM = """You are a Slay the Spire combat strategist. You receive a full opening snapshot (hand, piles, master deck, enemies, relics).

Write an advisory battle guide for the entire fight. The in-game agent will see updated state each turn and may deviate from this plan.

Use markdown with these headings (keep each section brief):
## Win condition
## Kill order and priorities
## Defense and spike damage
## Relic and power synergies
## Draw order and scaling notes

Do not emit game commands or <final_decision> tags. Plain markdown only."""


def build_prompt_sections(
    vm: dict[str, Any],
    recent_actions: list[str],
    strategy_memory: list[str] | None = None,
    combat_plan_guide: str | None = None,
) -> list[tuple[str, str]]:
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
        player_lines.append(f"player_block={combat.get('player_block', 0)}")

    relic_lines = [_relic_line(r) for r in inventory.get("relics", [])]
    potion_lines = []
    for idx, potion in enumerate(inventory.get("potions", []), start=1):
        effect = ((potion.get("kb") or {}).get("effect")) or ""
        line = f"{idx}. {potion.get('name', '?')}"
        if effect:
            line += f" | effect={effect}"
        potion_lines.append(line)

    hand_lines = [_card_line(card, idx, show_token=True) for idx, card in enumerate(combat.get("hand", []), start=1)]
    monster_lines = [
        _monster_line(monster, idx)
        for idx, monster in enumerate(combat.get("monsters", []), start=1)
        if not monster.get("is_gone")
    ]
    power_lines = [_power_line(power) for power in combat.get("player_powers", [])]

    screen_lines = [f"type={screen.get('type', 'NONE')}"]
    if screen.get("title"):
        screen_lines.append(f"title={screen.get('title')}")
    content = screen.get("content") or {}
    if content.get("grid_purpose"):
        screen_lines.append(f"purpose={content['grid_purpose']}")
    if content.get("screen_reason"):
        screen_lines.append(f"context={content['screen_reason']}")

    legal_lines = [
        f"{idx}. label={action.get('label', '?')} | command={action.get('command', '?')}"
        for idx, action in enumerate(legal_actions, start=1)
    ]

    valid_play_lines = _valid_play_lines(legal_actions)
    map_lines = _map_planning_lines(vm)
    recent_action_lines = recent_actions[-5:]
    screen_content_lines = _screen_content_lines(vm)

    buff_glossary_lines = _buff_glossary_lines(vm)

    play_syntax_lines = [
        "Use PLAY <card_token> <target_index> for targeted cards (target_index is 0-based, shown in MONSTERS).",
        "Use PLAY <card_token> for untargeted cards.",
        "card_token is the 6-char token shown in HAND lines. Enemy indices are stable even after kills.",
        "You may propose up to 5 commands per turn as a sequence. Include END when the turn should end.",
    ] if combat else []

    sections: list[tuple[str, str]] = [
        ("PLAYER STATE", _fmt_list(player_lines)),
        ("LEGAL ACTIONS", _fmt_list(legal_lines)),
        ("VALID PLAYS", _fmt_list(valid_play_lines, fallback="No playable cards.")),
        ("MONSTERS", _fmt_list(monster_lines)),
        ("HAND", _fmt_list(hand_lines)),
        ("PLAYER POWERS", _fmt_list(power_lines)),
        ("RELICS", _fmt_list(relic_lines)),
        ("POTIONS", _fmt_list(potion_lines)),
        ("CURRENT SCREEN", _fmt_list(screen_lines)),
        ("SCREEN CONTENT", _fmt_list(screen_content_lines, fallback="No content.")),
        (
            "RECENT EXECUTED ACTIONS",
            _fmt_list(recent_action_lines, fallback="No prior executed actions in this scene."),
        ),
        (
            "TOOLING NOTES",
            "- Use a pile inspection tool only if you need hidden pile details.\n"
            "- Use inspect_deck_summary for archetype/cost-curve checks.\n"
            "- Do not request a tool if the visible state already answers the question.",
        ),
    ]
    # Add card-choice guidance when in combat so the model considers damage and planning.
    if combat:
        idx_valid = next((i for i, (t, _) in enumerate(sections) if t == "VALID PLAYS"), -1)
        if idx_valid >= 0:
            sections.insert(
                idx_valid + 1,
                ("CARD CHOICE GUIDANCE", _fmt_list(CARD_CHOICE_GUIDANCE)),
            )
        if play_syntax_lines:
            idx_hand = next((i for i, (t, _) in enumerate(sections) if t == "HAND"), -1)
            if idx_hand >= 0:
                sections.insert(
                    idx_hand + 1,
                    ("PLAY SYNTAX", _fmt_list(play_syntax_lines)),
                )
    if strategy_memory:
        sections.insert(1, ("STRATEGY MEMORY", _fmt_list(strategy_memory)))
    guide = (combat_plan_guide or "").strip()
    if guide and combat:
        sm_idx = next((i for i, (t, _) in enumerate(sections) if t == "STRATEGY MEMORY"), -1)
        insert_at = sm_idx + 1 if sm_idx >= 0 else 1
        sections.insert(
            insert_at,
            ("COMBAT PLAN GUIDE (advisory — live state overrides)", guide),
        )
    if buff_glossary_lines:
        sections.insert(
            next(i for i, (t, _) in enumerate(sections) if t == "POTIONS") + 1,
            ("BUFF GLOSSARY (meanings of powers/tokens above)", _fmt_list(buff_glossary_lines)),
        )
    if map_lines:
        sections.insert(8, ("MAP PLANNING", _fmt_list(map_lines)))
    map_scene = _map_scene_lines(vm)
    if map_scene:
        sections.insert(9, ("MAP SCENE", _fmt_list(map_scene)))
    return sections


def build_user_prompt(
    vm: dict[str, Any],
    _state_id: str,
    recent_actions: list[str],
    strategy_memory: list[str] | None = None,
    combat_plan_guide: str | None = None,
) -> str:
    sections = build_prompt_sections(
        vm,
        recent_actions,
        strategy_memory=strategy_memory,
        combat_plan_guide=combat_plan_guide,
    )

    return "\n\n".join(f"## {title}\n{body}" for title, body in sections) + "\n"


def build_combat_planning_prompt(vm: dict[str, Any], *, max_cards_per_section: int = 80) -> str:
    """Rich one-shot context for LLM combat planning (opening snapshot)."""
    combat = vm.get("combat") or {}
    if not combat:
        return ""
    header = vm.get("header") or {}
    inventory = vm.get("inventory") or {}
    cap = max(10, max_cards_per_section)

    player_lines = [
        f"class={header.get('class', '?')}",
        f"floor={header.get('floor', '?')}",
        f"hp={header.get('hp_display', '?')}",
        f"gold={header.get('gold', '?')}",
        f"energy={header.get('energy', '?')}",
        f"turn={header.get('turn', '?')}",
        f"player_block={combat.get('player_block', 0)}",
    ]
    monster_lines = [
        _monster_line(monster, idx)
        for idx, monster in enumerate(combat.get("monsters", []), start=1)
        if not monster.get("is_gone")
    ]
    power_lines = [_power_line(power) for power in combat.get("player_powers", [])]
    relic_lines = [_relic_line(r) for r in inventory.get("relics", [])]
    potion_lines = []
    for idx, potion in enumerate(inventory.get("potions", []), start=1):
        effect = ((potion.get("kb") or {}).get("effect")) or ""
        line = f"{idx}. {potion.get('name', '?')}"
        if effect:
            line += f" | effect={effect}"
        potion_lines.append(line)

    def pile_section(title: str, cards: list[dict[str, Any]]) -> tuple[str, str]:
        slice_n = min(len(cards), cap)
        lines = [_card_line(c, i, show_token=False) for i, c in enumerate(cards[:slice_n], start=1)]
        omitted = len(cards) - slice_n
        body = _fmt_list(lines)
        if omitted > 0:
            body += f"\n- ... {omitted} more cards omitted (cap={cap})."
        return title, body

    hand_cards = combat.get("hand", []) or []
    draw_cards = combat.get("draw_pile", []) or []
    discard_cards = combat.get("discard_pile", []) or []
    exhaust_cards = combat.get("exhaust_pile", []) or []
    master_deck = inventory.get("deck", []) or []
    if not isinstance(master_deck, list):
        master_deck = []

    hand_lines = [_card_line(card, idx, show_token=True) for idx, card in enumerate(hand_cards, start=1)]
    _, draw_body = pile_section("DRAW PILE", draw_cards)
    _, discard_body = pile_section("DISCARD PILE", discard_cards)
    _, exhaust_body = pile_section("EXHAUST PILE", exhaust_cards)
    _, deck_body = pile_section("MASTER DECK (full run deck)", master_deck)

    sections: list[tuple[str, str]] = [
        ("PLANNING TASK", _fmt_list(["Produce a full-fight advisory guide from this opening snapshot only."])),
        ("PLAYER STATE", _fmt_list(player_lines)),
        ("MONSTERS", _fmt_list(monster_lines)),
        ("HAND", _fmt_list(hand_lines)),
        ("DRAW PILE", draw_body),
        ("DISCARD PILE", discard_body),
        ("EXHAUST PILE", exhaust_body),
        ("MASTER DECK", deck_body),
        ("PLAYER POWERS", _fmt_list(power_lines)),
        ("RELICS", _fmt_list(relic_lines)),
        ("POTIONS", _fmt_list(potion_lines)),
    ]
    preamble = (
        "You have full pile and deck lists (subject to per-section card caps). "
        "Reason about the whole combat; the tactical agent will get fresh snapshots each turn.\n\n"
    )
    return preamble + "\n\n".join(f"## {title}\n{body}" for title, body in sections) + "\n"


def format_pile_tool_result(tool_name: str, cards: list[dict[str, Any]]) -> str:
    lines = [_card_line(card, idx) for idx, card in enumerate(cards, start=1)]
    title = tool_name.replace("_", " ").title()
    return f"## TOOL RESULT: {title}\n{_fmt_list(lines)}"

