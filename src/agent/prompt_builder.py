from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agent.vm_shapes import as_dict, normalize_legal_actions, prompt_command_for_action
from src.repo_paths import REPO_ROOT
from src.ui.state_processor import event_option_choose_index

# Lazy-loaded map of buff/power name -> description (from buff_descriptions.json + powers)
_BUFF_DESCRIPTIONS: dict[str, str] | None = None
_ORB_MECHANICS: dict[str, Any] | None = None
_TOKEN_PATTERN = re.compile(r"\[([^\]]+)\]")


def _get_buff_descriptions() -> dict[str, str]:
    """Load buff_descriptions.json and merge with get_power_info for any missing names."""
    global _BUFF_DESCRIPTIONS
    if _BUFF_DESCRIPTIONS is not None:
        return _BUFF_DESCRIPTIONS
    path = REPO_ROOT / "data" / "processed" / "buff_descriptions.json"
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


def _get_orb_mechanics() -> dict[str, Any]:
    """Load orb_mechanics.json — canonical orb reference for prompts (shared with web UI)."""
    global _ORB_MECHANICS
    if _ORB_MECHANICS is not None:
        return _ORB_MECHANICS
    path = REPO_ROOT / "data" / "processed" / "orb_mechanics.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            _ORB_MECHANICS = json.load(f)
    else:
        _ORB_MECHANICS = {"global": {"bullets": []}, "types": {}, "ui": {}}
    return _ORB_MECHANICS


def _is_defect_class(vm: dict[str, Any]) -> bool:
    h = as_dict(vm.get("header"))
    return str(h.get("class", "")).strip().upper() == "DEFECT"


def _orb_type_meta(orb: dict[str, Any], types_map: dict[str, Any]) -> dict[str, Any]:
    oid = str(orb.get("id") or "").strip()
    name = str(orb.get("name") or "").strip()
    if oid and oid in types_map:
        m = types_map[oid]
        if isinstance(m, dict):
            return m
    if name and name in types_map:
        m = types_map[name]
        if isinstance(m, dict):
            return m
    d = types_map.get("_default")
    return d if isinstance(d, dict) else {}


def _orb_lines_for_prompt(orbs: list[Any]) -> list[str]:
    mechanics = _get_orb_mechanics()
    g = mechanics.get("global") if isinstance(mechanics.get("global"), dict) else {}
    bullets_raw = g.get("bullets")
    bullets = [str(b).strip() for b in bullets_raw] if isinstance(bullets_raw, list) else []
    bullets = [b for b in bullets if b]
    types_map = mechanics.get("types") if isinstance(mechanics.get("types"), dict) else {}
    out: list[str] = list(bullets)
    for i, raw in enumerate(orbs):
        if not isinstance(raw, dict):
            continue
        o = raw
        name = str(o.get("name", "?")).strip()
        pa = o.get("passive_amount")
        ea = o.get("evoke_amount")
        meta = _orb_type_meta(o, types_map)
        short = str(meta.get("short", "")).strip()
        pd = str(meta.get("passive_detail", "")).strip()
        ed = str(meta.get("evoke_detail", "")).strip()
        if name == "Orb Slot":
            out.append(
                f"slot {i} (index 0 = right-most / first in stack order): empty | "
                f"passive_amount={pa} evoke_amount={ea}"
            )
        else:
            detail = " | ".join(x for x in (short, pd, ed) if x)
            out.append(
                f"slot {i} (index 0 = right-most / first in stack order): {name} | "
                f"passive_amount={pa} evoke_amount={ea}"
                + (f" | {detail}" if detail else "")
            )
    return out


def _orb_subsection_body(vm: dict[str, Any]) -> str | None:
    if not _is_defect_class(vm):
        return None
    combat = as_dict(vm.get("combat"))
    if not combat:
        return None
    orbs = combat.get("player_orbs")
    if not isinstance(orbs, list) or len(orbs) == 0:
        return None
    return _fmt_list(_orb_lines_for_prompt(orbs))


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


def _neows_lament_is_spent(relic: dict[str, Any]) -> bool:
    """Neow's Lament stays in CommunicationMod relic list after use; counter is positive while charges remain.

    Logs show: counter 2/1 = active, counter -2 (or <=0) = depleted. Do not treat other relics' counters
    (e.g. Burning Blood uses -1 for \"no counter\") — we only match id NeowsBlessing.
    """
    if str(relic.get("id") or "").strip() != "NeowsBlessing":
        return False
    c = relic.get("counter")
    if c is None:
        return False
    try:
        v = int(c)
    except (TypeError, ValueError):
        return False
    return v <= 0


def _potion_row_name(p: dict[str, Any]) -> str:
    return str(p.get("name") or p.get("id") or "").strip()


def _potion_inventory_has_no_empty_slots(potions: Any) -> bool:
    """True when the inventory lists no ``Potion Slot`` row — no visible free slot, even if there are 4+ potions."""
    if not isinstance(potions, list) or not potions:
        return False
    saw_named_potion = False
    for p in potions:
        if not isinstance(p, dict):
            continue
        name = _potion_row_name(p)
        if name == "Potion Slot":
            return False
        if name:
            saw_named_potion = True
    return saw_named_potion


def _vm_offers_potion_acquire(vm: dict[str, Any]) -> bool:
    """Screen offers taking or buying a potion (combat reward, shop, or event option mentioning potions)."""
    screen = as_dict(vm.get("screen"))
    st = str(screen.get("type") or "")
    content = as_dict(screen.get("content"))
    if st == "COMBAT_REWARD":
        for r in content.get("rewards") or []:
            if isinstance(r, dict) and str(r.get("reward_type") or "").upper() == "POTION":
                return True
        return False
    if st == "SHOP_SCREEN":
        return bool(content.get("shop_potions"))
    if st == "EVENT":
        for opt in content.get("options") or []:
            if not isinstance(opt, dict):
                continue
            blob = f"{opt.get('label', '')} {opt.get('text', '')}".lower()
            if "potion" in blob:
                return True
        return False
    return False


def _fmt_list(items: list[str], fallback: str = "None") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {fallback}"


@dataclass
class PromptSubsection:
    title: str
    body: str
    profile_key: str | None = None


@dataclass
class PromptGroup:
    title: str
    subsections: list[PromptSubsection] = field(default_factory=list)


def _render_hierarchical(groups: list[PromptGroup]) -> str:
    blocks: list[str] = []
    for g in groups:
        if not g.subsections:
            continue
        inner = "\n\n".join(f"### {sub.title}\n{sub.body}" for sub in g.subsections)
        blocks.append(f"## {g.title}\n\n{inner}")
    return "\n\n".join(blocks) + "\n"


def _apply_prompt_profile(groups: list[PromptGroup], profile: str) -> list[PromptGroup]:
    """Minimal profile drops secondary context for ablation experiments."""
    p = (profile or "default").strip().lower()
    if p != "minimal":
        return groups
    drop_keys = {"buff_glossary", "map_scene", "card_choice_guidance"}
    thin_tooling = (
        "- Pile tools only if hidden information is required.\n"
        "- inspect_deck_summary for deck stats.\n"
        "- END: chosen_commands must be [\"END\"] alone, never queued with plays."
    )
    out: list[PromptGroup] = []
    for g in groups:
        kept: list[PromptSubsection] = []
        for sub in g.subsections:
            if sub.profile_key in drop_keys:
                continue
            if sub.profile_key == "tooling_notes":
                kept.append(PromptSubsection(sub.title, thin_tooling, sub.profile_key))
            else:
                kept.append(sub)
        if kept:
            out.append(PromptGroup(g.title, kept))
    return out


def _combat_screen_context_worth_showing(screen_lines: list[str]) -> bool:
    if len(screen_lines) > 1:
        return True
    if not screen_lines:
        return False
    return screen_lines[0].strip() != "type=NONE"


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
    """Format a single power with name, amount, KB type (buff/debuff), and effect for the prompt."""
    name = power.get("name", "?")
    amount = power.get("amount", "?")
    kb = power.get("kb") or {}
    effect = kb.get("effect", "")
    ptype = str(kb.get("type") or "").strip()
    parts: list[str] = [f"{name}({amount})"]
    if ptype:
        parts.append(f"type={ptype}")
    if effect:
        parts.append(f"effect={_compact_text(effect, limit=120)}")
    return " | ".join(parts)


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
    if _neows_lament_is_spent(relic):
        nm = relic.get("name") or "Neow's Lament"
        return (
            f"{nm} | "
            "desc=(spent — counter exhausted in game state; no longer sets enemies to 1 HP; ignore reference text)"
        )
    kb = relic.get("kb") or {}
    desc = kb.get("description", "")
    c = relic.get("counter")
    extra = ""
    if str(relic.get("id") or "").strip() == "NeowsBlessing" and c is not None:
        try:
            n = int(c)
            if n > 0:
                extra = f" | lament_elite_charges_remaining={n}"
        except (TypeError, ValueError):
            pass
    name = relic.get("name", "?")
    base = f"{name} | desc={desc}" if desc else name
    return base + extra if extra else base


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

    # Tokens in relic descriptions (skip spent Neow's Lament — KB text still claims 1-HP effect)
    for r in (vm.get("inventory") or {}).get("relics", []):
        if _neows_lament_is_spent(r):
            continue
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
        lines.append(
            "YOU DO NOT NEED TO TAKE A CARD ON THIS SCREEN. SKIP IS ALWAYS VALID AND OFTEN THE RIGHT CHOICE."
        )
        lines.append(
            "TAKING A CARD IS OPTIONAL — IT ONLY HELPS YOU BUILD A STRONGER DECK WHEN A PICK FITS YOUR PLAN."
        )
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
            kb_choice = kb_choices[i] if i < len(kb_choices) else None
            if isinstance(kb_choice, str):
                outcome = _compact_text(kb_choice, limit=120)
            elif isinstance(kb_choice, dict):
                outcome = _compact_text(kb_choice.get("outcome", ""), limit=120)
            else:
                outcome = ""
            # Match CommunicationMod ``choose N``: use choice_index for choosable rows; list row for disabled.
            if disabled:
                line = f"[row {i}] {label}"
            else:
                cmd_i = event_option_choose_index(opt, i)
                line = f"{cmd_i}. {label}"
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

    elif screen_type == "SHOP_ROOM":
        lines.append(
            "Shop entrance: inventory is not shown on this screen — you must enter the shop first. "
            "To browse and buy, use the legal action that opens the shop (e.g. `choose shop`). "
            "Use PROCEED only if you mean to leave without shopping."
        )
        choices = content.get("choices") or []
        if choices:
            lines.append("Available choices: " + ", ".join(str(c) for c in choices))

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


# Shown next to HAND in combat prompts (engine behavior).
HAND_SIZE_ENGINE_NOTE = (
    "Maximum hand size is 10. Any cards you would get beyond that are just gone—"
    "they never enter HAND; the rest of your deck stays in the draw pile."
)


# Guidance injected into the user prompt when making card/combat decisions.
CARD_CHOICE_GUIDANCE = [
    "Maximize damage long term and minimize health loss long term.",
    "Plan ahead: consider next turn, remaining enemies, and what you might draw.",
    "Do damage calculations when choosing attacks and targets (enemy block, Vulnerable, Weak, multi-hit).",
    "Prefer lines that kill or heavily weaken the most dangerous enemy when possible.",
    "Use block and debuffs when they prevent more damage than alternative plays.",
    "Never put END in chosen_commands together with other commands. END must be a separate decision: "
    "after your plays execute and the snapshot updates, respond again with chosen_commands:[\"END\"] only.",
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


def build_prompt_groups(
    vm: dict[str, Any],
    recent_actions: list[str],
    strategy_memory: list[str] | None = None,
    combat_plan_guide: str | None = None,
    prompt_profile: str = "default",
) -> list[PromptGroup]:
    header = as_dict(vm.get("header"))
    inventory = as_dict(vm.get("inventory"))
    combat = as_dict(vm.get("combat"))
    screen = as_dict(vm.get("screen"))
    legal_actions = normalize_legal_actions(vm.get("actions") or [])

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

    relic_lines = [_relic_line(r) for r in inventory.get("relics", []) if isinstance(r, dict)]
    potion_lines = []
    for idx, potion in enumerate(inventory.get("potions", []), start=1):
        if not isinstance(potion, dict):
            continue
        effect = ((potion.get("kb") or {}).get("effect")) or ""
        line = f"{idx}. {potion.get('name', '?')}"
        if effect:
            line += f" | effect={effect}"
        potion_lines.append(line)

    if _potion_inventory_has_no_empty_slots(inventory.get("potions")) and _vm_offers_potion_acquire(vm):
        potion_lines.append(
            "If you see no empty potion slots in the Potions list above, discard one first (e.g. "
            "POTION DISCARD <slot> from LEGAL ACTIONS) before you can take or buy another potion."
        )

    hand_lines = [
        _card_line(card, idx, show_token=True)
        for idx, card in enumerate(
            [c for c in combat.get("hand", []) if isinstance(c, dict)],
            start=1,
        )
    ]
    monster_lines = [
        _monster_line(monster, idx)
        for idx, monster in enumerate(
            [m for m in combat.get("monsters", []) if isinstance(m, dict)],
            start=1,
        )
        if not monster.get("is_gone")
    ]
    power_lines = [
        _power_line(power)
        for power in combat.get("player_powers", [])
        if isinstance(power, dict)
    ]

    screen_lines = [f"type={screen.get('type', 'NONE')}"]
    if screen.get("title"):
        screen_lines.append(f"title={screen.get('title')}")
    content = screen.get("content") or {}
    if content.get("grid_purpose"):
        screen_lines.append(f"purpose={content['grid_purpose']}")
    if content.get("screen_reason"):
        screen_lines.append(f"context={content['screen_reason']}")

    legal_lines = [
        f"{idx}. label={action.get('label', '?')} | command={prompt_command_for_action(action)}"
        for idx, action in enumerate(legal_actions, start=1)
    ]

    map_lines = _map_planning_lines(vm)
    map_scene = _map_scene_lines(vm)
    recent_action_lines = recent_actions[-5:]
    screen_content_lines = _screen_content_lines(vm)

    buff_glossary_lines = _buff_glossary_lines(vm)

    tooling_body = (
        "- Use a pile inspection tool only if you need hidden pile details.\n"
        "- Use inspect_deck_summary for archetype/cost-curve checks.\n"
        "- Do not request a tool if the visible state already answers the question.\n"
        "- END (end turn): chosen_commands must be [\"END\"] alone — never queue END with plays or potions."
    )

    groups: list[PromptGroup] = []

    run_subs: list[PromptSubsection] = [
        PromptSubsection("Player snapshot", _fmt_list(player_lines)),
    ]
    if strategy_memory:
        run_subs.append(PromptSubsection("Strategy memory", _fmt_list(strategy_memory)))
    guide = (combat_plan_guide or "").strip()
    if guide and combat:
        run_subs.append(
            PromptSubsection("Combat plan guide (advisory — live state overrides)", guide),
        )
    groups.append(PromptGroup("Run context", run_subs))

    load_subs: list[PromptSubsection] = [
        PromptSubsection("Relics", _fmt_list(relic_lines)),
        PromptSubsection("Potions", _fmt_list(potion_lines)),
    ]
    orb_body = _orb_subsection_body(vm)
    if orb_body:
        load_subs.append(PromptSubsection("ORBS", orb_body))
    if buff_glossary_lines:
        load_subs.append(
            PromptSubsection(
                "BUFF GLOSSARY (meanings of powers/tokens above)",
                _fmt_list(buff_glossary_lines),
                profile_key="buff_glossary",
            ),
        )
    groups.append(PromptGroup("Loadout", load_subs))

    if combat:
        sit_subs: list[PromptSubsection] = []
        if monster_lines:
            sit_subs.append(PromptSubsection("MONSTERS", _fmt_list(monster_lines)))
        if hand_lines:
            sit_subs.append(PromptSubsection("HAND", _fmt_list(hand_lines)))
        sit_subs.append(
            PromptSubsection("Hand capacity", _fmt_list([HAND_SIZE_ENGINE_NOTE])),
        )
        if power_lines:
            sit_subs.append(PromptSubsection("PLAYER POWERS", _fmt_list(power_lines)))
        if _combat_screen_context_worth_showing(screen_lines):
            sit_subs.append(PromptSubsection("Screen context", _fmt_list(screen_lines)))
        if screen_content_lines:
            sit_subs.append(PromptSubsection("Scene body", _fmt_list(screen_content_lines)))
        if sit_subs:
            groups.append(PromptGroup("Combat situation", sit_subs))
    else:
        nc_subs: list[PromptSubsection] = [
            PromptSubsection("Screen header", _fmt_list(screen_lines)),
            PromptSubsection(
                "Scene body",
                _fmt_list(screen_content_lines, fallback="No content."),
            ),
        ]
        if map_lines:
            nc_subs.append(PromptSubsection("Map planning", _fmt_list(map_lines)))
        if map_scene:
            nc_subs.append(
                PromptSubsection(
                    "Map scene",
                    _fmt_list(map_scene),
                    profile_key="map_scene",
                ),
            )
        groups.append(PromptGroup("Current scene", nc_subs))

    if combat:
        groups.append(
            PromptGroup(
                "Turn heuristics",
                [
                    PromptSubsection(
                        "CARD CHOICE GUIDANCE",
                        _fmt_list(CARD_CHOICE_GUIDANCE),
                        profile_key="card_choice_guidance",
                    ),
                ],
            ),
        )

    groups.append(
        PromptGroup(
            "History & tools",
            [
                PromptSubsection(
                    "RECENT EXECUTED ACTIONS",
                    _fmt_list(
                        recent_action_lines,
                        fallback="No prior executed actions in this scene.",
                    ),
                ),
                PromptSubsection(
                    "TOOLING NOTES",
                    tooling_body,
                    profile_key="tooling_notes",
                ),
            ],
        ),
    )

    groups.append(
        PromptGroup(
            "What you can do",
            [PromptSubsection("LEGAL ACTIONS", _fmt_list(legal_lines))],
        ),
    )

    return _apply_prompt_profile(groups, prompt_profile)


def build_user_prompt(
    vm: dict[str, Any],
    _state_id: str,
    recent_actions: list[str],
    strategy_memory: list[str] | None = None,
    combat_plan_guide: str | None = None,
    prompt_profile: str = "default",
) -> str:
    from src.agent.config import get_agent_config

    groups = build_prompt_groups(
        vm,
        recent_actions,
        strategy_memory=strategy_memory,
        combat_plan_guide=combat_plan_guide,
        prompt_profile=prompt_profile,
    )
    main = _render_hierarchical(groups)
    cfg = get_agent_config()
    path = cfg.resolved_strategy_corpus_path()
    if path and path.is_file():
        corpus = path.read_text(encoding="utf-8").strip()
        if corpus:
            header = (
                "## COMMUNITY STRATEGY NOTES (synthesized reference; see corpus file header for attribution)\n"
            )
            return header + corpus + "\n\n" + main
    return main


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
    if _is_defect_class(vm):
        porbs = combat.get("player_orbs")
        if isinstance(porbs, list) and len(porbs) > 0:
            sections.append(("ORBS", _fmt_list(_orb_lines_for_prompt(porbs))))
    preamble = (
        "You have full pile and deck lists (subject to per-section card caps). "
        "Reason about the whole combat; the tactical agent will get fresh snapshots each turn.\n\n"
    )
    return preamble + "\n\n".join(f"## {title}\n{body}" for title, body in sections) + "\n"


def format_pile_tool_result(tool_name: str, cards: list[dict[str, Any]]) -> str:
    lines = [_card_line(card, idx) for idx, card in enumerate(cards, start=1)]
    title = tool_name.replace("_", " ").title()
    return f"## TOOL RESULT: {title}\n{_fmt_list(lines)}"

