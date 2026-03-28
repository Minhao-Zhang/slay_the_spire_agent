"""
Transforms raw CommunicationMod game state into a display-ready view model,
enriching every entity with knowledge-base descriptions.
"""
from typing import Any, Optional

from src.reference.knowledge_base import (
    get_parsed_card_info,
    get_relic_info,
    get_monster_info,
    get_event_info,
    get_power_info,
    get_potion_info,
)


def process_state(raw: dict) -> dict:
    """Top-level entry point. Accepts a raw state dict (possibly wrapped in
    ``{"state": ...}``) and returns the view model consumed by the frontend."""
    state = raw.get("state", raw)
    action = raw.get("action")

    vm: dict[str, Any] = {
        "in_game": state.get("in_game", False),
        "header": None,
        "actions": [],
        "combat": None,
        "screen": None,
        "inventory": None,
        "map": None,
        "sidebar": None,
        "last_action": action,
    }

    if not vm["in_game"]:
        vm["header"] = {"class": "Main Menu", "floor": "-", "gold": "-",
                        "hp_display": "-", "energy": "-", "turn": "-"}
        return vm

    game = state.get("game_state", {})
    commands = state.get("available_commands", [])
    combat = game.get("combat_state")
    screen_type = game.get("screen_type", "NONE")
    screen_state = game.get("screen_state") or {}

    # -- header -- (player_block is passed explicitly to the LLM via combat.player_block, not in hp_display)
    hp_display = f"{game.get('current_hp', '?')}/{game.get('max_hp', '?')}"

    vm["header"] = {
        "class": game.get("class", "?"),
        "floor": game.get("floor", "?"),
        "gold": game.get("gold", "?"),
        "hp_display": hp_display,
        "energy": combat["player"]["energy"] if combat else "-",
        "turn": combat["turn"] if combat else "-",
    }

    # -- inventory (always present when in-game) --
    vm["inventory"] = {
        "relics": [_enrich_relic(r) for r in game.get("relics", [])],
        "potions": [_enrich_potion(p) for p in game.get("potions", [])],
        "deck": [_enrich_card(c) for c in game.get("deck", [])],
    }

    # -- combat --
    if combat:
        vm["combat"] = {
            "hand": [_enrich_card(c) for c in combat.get("hand", [])],
            "draw_pile": [_enrich_card(c) for c in combat.get("draw_pile", [])],
            "discard_pile": [_enrich_card(c) for c in combat.get("discard_pile", [])],
            "exhaust_pile": [_enrich_card(c) for c in combat.get("exhaust_pile", [])],
            "monsters": [_enrich_monster(m) for m in combat.get("monsters", [])],
            "player_powers": [_enrich_power(p) for p in combat.get("player", {}).get("powers", [])],
            "player_block": combat.get("player", {}).get("block", 0),
            "player_orbs": combat.get("player", {}).get("orbs", []),
        }

    # -- screen --
    if screen_type and screen_type != "NONE":
        vm["screen"] = _build_screen(screen_type, screen_state, game, combat)

    # -- map (always pass through for client-side SVG rendering) --
    if game.get("map"):
        boss_name = game.get("act_boss")
        vm["map"] = {
            "nodes": game["map"],
            "current_node": screen_state.get("current_node") if screen_type == "MAP" else None,
            "next_nodes": screen_state.get("next_nodes") if screen_type == "MAP" else None,
            "boss_available": screen_state.get("boss_available", False) if screen_type == "MAP" else False,
            "boss_name": boss_name,
            "boss_kb": _safe_monster_kb(boss_name) if boss_name else None,
        }

    # -- sidebar (for screen-overlay views) --
    vm["sidebar"] = {
        "floor": game.get("floor"),
        "hp_display": hp_display,
        "gold": game.get("gold"),
        "relics": vm["inventory"]["relics"],
        "potions": vm["inventory"]["potions"],
    }

    # -- actions (legal commands; main.py uses len(vm["actions"]) == 1 to short-circuit and skip the LLM) --
    vm["actions"] = _build_actions(commands, game, combat, screen_type, screen_state)

    return vm


# ---------------------------------------------------------------------------
# Entity enrichment helpers
# ---------------------------------------------------------------------------

def _enrich_card(card: dict) -> dict:
    """Add KB description to a card dict."""
    out = dict(card)
    kb = get_parsed_card_info(card.get("name", ""), card.get("upgrades", 0))
    if kb:
        out["kb"] = {
            "description": kb.get("description", ""),
            "character": kb.get("character", ""),
            "type": kb.get("type", card.get("type", "")),
        }
    else:
        out["kb"] = None
    return out


def _enrich_relic(relic: dict) -> dict:
    out = dict(relic)
    kb = get_relic_info(relic.get("name", ""))
    if kb:
        out["kb"] = {
            "description": kb.get("description", ""),
        }
    else:
        out["kb"] = None
    return out


def _enrich_potion(potion: dict) -> dict:
    out = dict(potion)
    kb = get_potion_info(potion.get("name", ""))
    if kb:
        out["kb"] = {"effect": kb.get("effect", "")}
    else:
        out["kb"] = None
    return out


def _enrich_power(power: dict) -> dict:
    out = dict(power)
    kb = get_power_info(power.get("name", ""))
    if kb:
        out["kb"] = {
            "effect": kb.get("effect", ""),
            "type": kb.get("type", ""),
            "stacks": kb.get("stacks", ""),
        }
    else:
        out["kb"] = None
    return out


def _enrich_monster(monster: dict) -> dict:
    out = dict(monster)
    # Compute display strings (block is passed explicitly to the LLM, not embedded in hp_display)
    out["hp_display"] = f"{monster.get('current_hp', '?')}/{monster.get('max_hp', '?')}"

    dmg = monster.get("move_base_damage", -1)
    hits = monster.get("move_hits", 1)
    if dmg and dmg > 0:
        adj = monster.get("move_adjusted_damage", dmg)
        out["intent_display"] = f"Attack: {adj}x{hits}" if hits > 1 else f"Attack: {adj}"
    else:
        out["intent_display"] = f"Intent: {monster.get('intent', '?')}"

    out["powers"] = [_enrich_power(p) for p in monster.get("powers", [])]

    kb = get_monster_info(monster.get("name", ""))
    if kb:
        out["kb"] = {
            "hp_range": kb.get("hp") or "",
            "moves": kb.get("moves") or [],
            "notes": kb.get("notes") or "",
            "ai": kb.get("ai") or "",
        }
    else:
        out["kb"] = None
    return out


def _safe_monster_kb(name: str) -> Optional[dict]:
    kb = get_monster_info(name)
    if not kb:
        return None
    return {
        "hp_range": kb.get("hp") or "",
        "moves": kb.get("moves") or [],
        "notes": kb.get("notes") or "",
        "ai": kb.get("ai") or "",
    }


_REST_OPTION_META = {
    "rest": ("Rest", "Heal for 30% of your max HP."),
    "smith": ("Smith", "Upgrade a card in your deck."),
    "lift": ("Lift", "Gain 1 Strength (Girya)."),
    "toke": ("Toke", "Remove a card from your deck (Peace Pipe)."),
    "dig": ("Dig", "Obtain a random relic (Shovel)."),
    "recall": ("Recall", "Add a card to your deck (Dream Catcher)."),
}


# ---------------------------------------------------------------------------
# Screen builder
# ---------------------------------------------------------------------------

# Human-readable context for HAND_SELECT when triggered by a relic/action (from combat_state.current_action).
# This is passed to the LLM and debugger so the AI knows why cards are being chosen (e.g. Gambling Chip).
_HAND_SELECT_ACTION_MESSAGES: dict[str, str] = {
    "GamblingChipAction": "Choose Any Number of Cards to Replace (Gambling Chip)",
}


def _hand_select_screen_reason(combat: Optional[dict]) -> str:
    """Build a clear reason for HAND_SELECT (e.g. Gambling Chip) for the LLM and debugger."""
    if not combat:
        return ""
    action = (combat.get("current_action") or "").strip()
    if not action:
        return ""
    return _HAND_SELECT_ACTION_MESSAGES.get(action) or f"Hand select (reason: {action})"


def _build_screen(screen_type: str, s: dict, game: dict, combat: Optional[dict]) -> dict:
    screen: dict[str, Any] = {
        "type": screen_type,
        "title": screen_type.replace("_", " "),
        "content": {},
    }

    if screen_type == "EVENT":
        event_kb = get_event_info(s.get("event_name", "")) if s.get("event_name") else None
        screen["content"] = {
            "body_text": s.get("body_text", ""),
            "options": [
                {
                    "label": o.get("label", f"Option {i}"),
                    "text": o.get("text", ""),
                    "disabled": o.get("disabled", False),
                    "choice_index": i,
                }
                for i, o in enumerate(s.get("options", []))
            ],
            "event_kb": {
                "name": event_kb.get("name", ""),
                "choices": event_kb.get("choices", []),
                "is_shrine": event_kb.get("is_shrine", False),
            } if event_kb else None,
        }

    elif screen_type == "MAP":
        screen["content"] = {
            "current_node": s.get("current_node"),
            "next_nodes": s.get("next_nodes", []),
            "boss_available": s.get("boss_available", False),
            "current_pos_label": (
                f"Floor {game.get('floor', '?')} - x:{s['current_node']['x']} y:{s['current_node']['y']}"
                if s.get("current_node") else "Selecting first node"
            ),
        }

    elif screen_type == "COMBAT_REWARD":
        rewards = []
        for i, r in enumerate(s.get("rewards", [])):
            rtype = r.get("reward_type", "")
            if rtype == "GOLD":
                label = f"{r.get('gold', '?')} Gold"
            elif rtype == "POTION":
                pname = r.get("potion", {}).get("name", "Potion")
                label = f"Potion: {pname}"
            elif rtype == "RELIC":
                rname = r.get("relic", {}).get("name", "Relic")
                label = f"Relic: {rname}"
                relic_kb = get_relic_info(rname)
                r["relic_kb"] = {
                    "description": relic_kb.get("description", ""),
                } if relic_kb else None
            elif rtype == "CARD":
                label = "Card Reward (Draft)"
            else:
                label = rtype
            rewards.append({**r, "label": label, "choice_index": i})
        screen["content"] = {"rewards": rewards}

    elif screen_type == "CARD_REWARD":
        screen["content"] = {
            "cards": [_enrich_card(c) for c in s.get("cards", [])],
        }

    elif screen_type == "REST":
        screen["content"] = {
            "rest_options": [
                {
                    "label": _REST_OPTION_META.get(o, (o.title(), ""))[0],
                    "description": _REST_OPTION_META.get(o, (o.title(), ""))[1],
                    "choice_name": o,
                }
                for o in s.get("rest_options", [])
            ],
            "has_rested": s.get("has_rested", False),
        }

    elif screen_type in ("GRID", "HAND_SELECT"):
        cards = s.get("cards") or s.get("hand") or []
        content: dict[str, Any] = {
            "cards": [_enrich_card(c) for c in cards],
            "num_cards": s.get("num_cards", s.get("max_cards", 1)),
        }
        # Propagate intent flags so the LLM knows whether this is add/remove/upgrade/transform
        if s.get("for_purge"):
            content["grid_purpose"] = "REMOVE"
            screen["title"] = "Choose a card to REMOVE from your deck"
        elif s.get("for_upgrade"):
            content["grid_purpose"] = "UPGRADE"
            screen["title"] = "Choose a card to UPGRADE"
        elif s.get("for_transform"):
            content["grid_purpose"] = "TRANSFORM"
            screen["title"] = "Choose a card to TRANSFORM"
        if screen_type == "HAND_SELECT":
            reason = _hand_select_screen_reason(combat)
            if reason:
                content["screen_reason"] = reason
                screen["title"] = reason
        screen["content"] = content

    elif screen_type == "SHOP_ROOM":
        screen["title"] = "SHOP"
        screen["content"] = {
            "choices": game.get("choice_list", []),
        }

    elif screen_type == "SHOP_SCREEN":
        screen["title"] = "SHOP"
        shop_cards = [_enrich_card(c) for c in s.get("cards", [])]
        shop_relics = []
        for i, r in enumerate(s.get("relics", [])):
            enriched = _enrich_relic(r)
            enriched["choice_index"] = len(s.get("cards", [])) + i
            shop_relics.append(enriched)
        shop_potions = []
        for i, p in enumerate(s.get("potions", [])):
            enriched = _enrich_potion(p)
            enriched["choice_index"] = len(s.get("cards", [])) + len(s.get("relics", [])) + i
            shop_potions.append(enriched)

        screen["content"] = {
            "gold": game.get("gold", 0),
            "shop_cards": shop_cards,
            "shop_relics": shop_relics,
            "shop_potions": shop_potions,
            "purge_available": s.get("purge_available", False),
            "purge_cost": s.get("purge_cost", 0),
        }

    elif screen_type == "CHEST":
        screen["title"] = "TREASURE"
        screen["content"] = {
            "chest_type": s.get("chest_type", "Unknown"),
            "chest_open": s.get("chest_open", False),
        }

    elif screen_type == "BOSS_REWARD":
        screen["content"] = {
            "relics": [_enrich_relic(r) for r in s.get("relics", [])],
        }

    elif screen_type == "GAME_OVER":
        screen["content"] = {
            "score": s.get("score", 0),
            "victory": s.get("victory", False),
        }

    elif screen_type == "COMPLETE":
        screen["content"] = {}

    else:
        screen["content"] = {
            "choices": game.get("choice_list", []),
            "raw_screen_state": s,
        }

    return screen


# ---------------------------------------------------------------------------
# Action builder
# ---------------------------------------------------------------------------
# When the game sends only "confirm" in available_commands (e.g. after hand select
# / choose card to discard), vm["actions"] has one entry and main.py short-circuits (no LLM).

_COMMAND_BUTTONS = [
    ("proceed", "PROCEED", "PROCEED", "primary"),
    ("end",     "END TURN", "END", "danger"),
    ("cancel",  "CANCEL", "CANCEL", "secondary"),
    ("leave",   "LEAVE", "LEAVE", "secondary"),
    ("skip",    "SKIP", "SKIP", "secondary"),
    ("confirm", "CONFIRM", "CONFIRM", "primary"),
    ("return",  "RETURN", "RETURN", "secondary"),
]


def _build_actions(commands: list, game: dict, combat: Optional[dict],
                   screen_type: str, screen_state: dict) -> list[dict]:
    actions: list[dict] = []

    for cmd_key, label, command, style in _COMMAND_BUTTONS:
        if cmd_key in commands:
            actions.append({"label": label, "command": command, "style": style})

    # Play cards in combat
    if "play" in commands and combat:
        hand = combat.get("hand", [])
        energy = combat.get("player", {}).get("energy", 0)
        monsters = combat.get("monsters", [])
        for i, card in enumerate(hand):
            if not card.get("is_playable") or card.get("cost", 99) > energy:
                continue
            uuid_full = card.get("uuid", "")
            card_uuid_token = uuid_full[:6] if uuid_full else ""
            if card.get("has_target"):
                for mi, m in enumerate(monsters):
                    if not m.get("is_gone") and not m.get("half_dead"):
                        actions.append({
                            "label": f"{card['name']} \u2192 {m['name']}",
                            "command": f"PLAY {i + 1} {mi}",
                            "style": "success",
                            "card_uuid_token": card_uuid_token,
                            "hand_index": i + 1,
                            "monster_index": mi,
                        })
            else:
                actions.append({
                    "label": card["name"],
                    "command": f"PLAY {i + 1}",
                    "style": "primary",
                    "card_uuid_token": card_uuid_token,
                    "hand_index": i + 1,
                })

    # Use potions
    if "potion" in commands:
        for i, pot in enumerate(game.get("potions", [])):
            if pot.get("can_use"):
                if pot.get("requires_target") and combat:
                    for mi, m in enumerate(combat.get("monsters", [])):
                        if not m.get("is_gone") and not m.get("half_dead"):
                            actions.append({
                                "label": f"Use {pot['name']} \u2192 {m['name']}",
                                "command": f"POTION USE {i} {mi}",
                                "style": "primary",
                            })
                else:
                    actions.append({
                        "label": f"Use {pot['name']}",
                        "command": f"POTION USE {i}",
                        "style": "primary",
                    })
            if pot.get("can_discard"):
                actions.append({
                    "label": f"Discard {pot['name']}",
                    "command": f"POTION DISCARD {i}",
                    "style": "secondary",
                })

    # Choose actions depend on screen type
    if "choose" in commands:
        actions.extend(_build_choose_actions(screen_type, screen_state, game))

    return actions


def _build_choose_actions(screen_type: str, s: dict, game: dict) -> list[dict]:
    actions: list[dict] = []

    # Generic choosable item lists (hand select, grid, card rewards, etc.)
    items = s.get("hand") or s.get("cards") or s.get("relics") or s.get("rewards") or s.get("potions")

    if screen_type == "MAP" and s.get("next_nodes"):
        for i, n in enumerate(s["next_nodes"]):
            actions.append({
                "label": f"GO: {n.get('symbol', '?')}",
                "command": f"choose {i}",
                "style": "primary",
            })
        if s.get("boss_available"):
            actions.append({
                "label": "FIGHT BOSS",
                "command": "choose boss",
                "style": "danger",
            })

    elif screen_type == "EVENT" and s.get("options"):
        for i, o in enumerate(s["options"]):
            if not o.get("disabled"):
                actions.append({
                    "label": o.get("label", f"Select {i}"),
                    "command": f"choose {i}",
                    "style": "primary",
                })

    elif screen_type == "COMBAT_REWARD" and s.get("rewards"):
        for i, r in enumerate(s["rewards"]):
            rtype = r.get("reward_type", "")
            if rtype == "GOLD":
                label = f"Take {r.get('gold', '?')} Gold"
            elif rtype == "POTION":
                label = f"Take {r.get('potion', {}).get('name', 'Potion')}"
            elif rtype == "RELIC":
                label = f"Take {r.get('relic', {}).get('name', 'Relic')}"
            elif rtype == "CARD":
                label = "Reward: Card Draft"
            else:
                label = rtype
            actions.append({"label": label, "command": f"choose {i}", "style": "secondary"})

    elif screen_type == "SHOP_ROOM":
        for choice in game.get("choice_list", []):
            actions.append({
                "label": choice.title(),
                "command": f"choose {choice}",
                "style": "primary",
            })

    elif screen_type == "SHOP_SCREEN":
        for i, c in enumerate(s.get("cards", [])):
            actions.append({
                "label": f"Buy {c.get('name', '?')} ({c.get('price', '?')}g)",
                "command": f"choose {c.get('name', i)}",
                "style": "secondary",
            })
        for r in s.get("relics", []):
            actions.append({
                "label": f"Buy {r.get('name', '?')} ({r.get('price', '?')}g)",
                "command": f"choose {r.get('name', '?')}",
                "style": "secondary",
            })
        for p in s.get("potions", []):
            actions.append({
                "label": f"Buy {p.get('name', '?')} ({p.get('price', '?')}g)",
                "command": f"choose {p.get('name', '?')}",
                "style": "secondary",
            })
        if s.get("purge_available"):
            actions.append({
                "label": f"Remove Card ({s.get('purge_cost', '?')}g)",
                "command": "choose purge",
                "style": "danger",
            })

    elif screen_type == "CHEST":
        actions.append({"label": "Open Chest", "command": "choose open", "style": "primary"})

    elif screen_type == "REST" and s.get("rest_options"):
        for o in s["rest_options"]:
            label, _ = _REST_OPTION_META.get(o, (o.title(), ""))
            actions.append({
                "label": label,
                "command": f"choose {o}",
                "style": "primary",
            })

    elif screen_type == "BOSS_REWARD" and s.get("relics"):
        for i, r in enumerate(s["relics"]):
            actions.append({
                "label": r.get("name", f"Relic {i}"),
                "command": f"choose {i}",
                "style": "primary",
            })

    elif items:
        for i, it in enumerate(items):
            label = it.get("name") or it.get("reward_type") or it.get("label") or it.get("id") or f"Option {i}"
            actions.append({"label": label, "command": f"choose {i}", "style": "secondary"})

    else:
        for i, choice in enumerate(game.get("choice_list", [])):
            actions.append({"label": choice, "command": f"choose {i}", "style": "secondary"})

    return actions
