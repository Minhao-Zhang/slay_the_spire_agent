"""Build ``screen`` view dict + combat/inventory views with KB enrichment."""

from __future__ import annotations

from typing import Any

from src.domain.state_projection.kb_enrich import (
    enrich_card,
    enrich_monster,
    enrich_potion,
    enrich_power,
    enrich_relic,
)
from src.reference.knowledge_base import get_event_info


def _monster_view(m: dict[str, Any]) -> dict[str, Any]:
    out = dict(m)
    out["hp_display"] = f"{m.get('current_hp', '?')}/{m.get('max_hp', '?')}"
    dmg = m.get("move_base_damage", -1)
    hits = m.get("move_hits", 1)
    if dmg and dmg > 0:
        adj = m.get("move_adjusted_damage", dmg)
        out["intent_display"] = (
            f"Attack: {adj}x{hits}" if hits > 1 else f"Attack: {adj}"
        )
    else:
        out["intent_display"] = f"Intent: {m.get('intent', '?')}"
    return out


def build_screen_view(
    screen_type: str,
    screen_state: dict[str, Any],
    game: dict[str, Any],
    combat: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not screen_type or screen_type == "NONE":
        return None

    s = screen_state
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
            "event_kb": (
                {
                    "name": event_kb.get("name", ""),
                    "choices": event_kb.get("choices", []),
                    "is_shrine": event_kb.get("is_shrine", False),
                }
                if event_kb
                else None
            ),
        }

    elif screen_type == "MAP":
        screen["content"] = {
            "current_node": s.get("current_node"),
            "next_nodes": s.get("next_nodes", []),
            "boss_available": s.get("boss_available", False),
            "current_pos_label": (
                f"Floor {game.get('floor', '?')} - x:{s['current_node']['x']} y:{s['current_node']['y']}"
                if s.get("current_node")
                else "Selecting first node"
            ),
        }

    elif screen_type == "COMBAT_REWARD":
        rewards = []
        for i, r in enumerate(s.get("rewards", [])):
            row = dict(r)
            rtype = row.get("reward_type", "")
            if rtype == "GOLD":
                label = f"{row.get('gold', '?')} Gold"
            elif rtype == "POTION":
                pname = (row.get("potion") or {}).get("name", "Potion")
                label = f"Potion: {pname}"
                pot = row.get("potion")
                if isinstance(pot, dict):
                    row["potion"] = enrich_potion(dict(pot), game)
            elif rtype == "RELIC":
                rname = (row.get("relic") or {}).get("name", "Relic")
                label = f"Relic: {rname}"
                rel = row.get("relic")
                if isinstance(rel, dict):
                    row["relic"] = enrich_relic(dict(rel))
            elif rtype == "CARD":
                label = "Card Reward (Draft)"
            else:
                label = str(rtype)
            rewards.append({**row, "label": label, "choice_index": i})
        screen["content"] = {"rewards": rewards}

    elif screen_type == "CARD_REWARD":
        screen["content"] = {
            "cards": [enrich_card(dict(c)) for c in s.get("cards", [])],
        }

    elif screen_type == "REST":
        screen["content"] = {
            "rest_options": list(s.get("rest_options", [])),
            "has_rested": s.get("has_rested", False),
        }

    elif screen_type in ("GRID", "HAND_SELECT"):
        cards = s.get("cards") or s.get("hand") or []
        content: dict[str, Any] = {
            "cards": [enrich_card(dict(c)) for c in cards],
            "num_cards": s.get("num_cards", s.get("max_cards", 1)),
        }
        if s.get("for_purge"):
            content["grid_purpose"] = "REMOVE"
            screen["title"] = "Choose a card to REMOVE from your deck"
        elif s.get("for_upgrade"):
            content["grid_purpose"] = "UPGRADE"
            screen["title"] = "Choose a card to UPGRADE"
        elif s.get("for_transform"):
            content["grid_purpose"] = "TRANSFORM"
            screen["title"] = "Choose a card to TRANSFORM"
        if screen_type == "HAND_SELECT" and combat:
            action = (combat.get("current_action") or "").strip()
            if action == "GamblingChipAction":
                reason = "Choose Any Number of Cards to Replace (Gambling Chip)"
                content["screen_reason"] = reason
                screen["title"] = reason
        screen["content"] = content

    elif screen_type == "SHOP_ROOM":
        screen["title"] = "SHOP"
        screen["content"] = {"choices": list(game.get("choice_list", []))}

    elif screen_type == "SHOP_SCREEN":
        screen["title"] = "SHOP"
        screen["content"] = {
            "gold": game.get("gold", 0),
            "shop_cards": [enrich_card(dict(c)) for c in s.get("cards", [])],
            "shop_relics": [enrich_relic(dict(r)) for r in s.get("relics", [])],
            "shop_potions": [enrich_potion(dict(p), game) for p in s.get("potions", [])],
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
            "relics": [enrich_relic(dict(r)) for r in s.get("relics", [])],
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
            "choices": list(game.get("choice_list", [])),
            "raw_screen_state": s,
        }

    return screen


def build_combat_view(combat: dict[str, Any]) -> dict[str, Any]:
    return {
        "hand": [enrich_card(dict(c)) for c in combat.get("hand", [])],
        "draw_pile": [enrich_card(dict(c)) for c in combat.get("draw_pile", [])],
        "discard_pile": [enrich_card(dict(c)) for c in combat.get("discard_pile", [])],
        "exhaust_pile": [enrich_card(dict(c)) for c in combat.get("exhaust_pile", [])],
        "monsters": [
            enrich_monster(_monster_view(m)) for m in combat.get("monsters", [])
        ],
        "player_powers": [
            enrich_power(dict(p))
            for p in (combat.get("player") or {}).get("powers", [])
        ],
        "player_block": (combat.get("player") or {}).get("block", 0),
        "player_orbs": list((combat.get("player") or {}).get("orbs", [])),
    }


def build_inventory_view(game: dict[str, Any]) -> dict[str, Any]:
    return {
        "relics": [enrich_relic(dict(r)) for r in game.get("relics", [])],
        "potions": [enrich_potion(dict(p), game) for p in game.get("potions", [])],
        "deck": [enrich_card(dict(c)) for c in game.get("deck", [])],
    }
