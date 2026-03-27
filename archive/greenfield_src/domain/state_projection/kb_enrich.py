"""Attach ``kb`` blobs from ``data/processed`` to view-model entities (UI + LLM)."""

from __future__ import annotations

from typing import Any

from src.reference.knowledge_base import (
    get_monster_info,
    get_parsed_card_info,
    get_parsed_potion_info,
    get_power_info,
    get_relic_info,
)


def _has_sacred_bark(game: dict[str, Any]) -> bool:
    for r in game.get("relics") or []:
        nm = str(r.get("name") or "").lower().replace("'", "")
        if "sacred bark" in nm or nm == "sacred bark":
            return True
    return False


def enrich_card(card: dict[str, Any]) -> dict[str, Any]:
    out = dict(card)
    upgrades = int(card.get("upgrades") or 0)
    kb = get_parsed_card_info(card.get("name", ""), upgrades)
    if kb:
        out["kb"] = {
            "description": kb.get("description", ""),
            "rarity": kb.get("rarity", ""),
            "character": kb.get("character", ""),
            "type": kb.get("type", card.get("type", "")),
        }
    else:
        out["kb"] = None
    return out


def enrich_relic(relic: dict[str, Any]) -> dict[str, Any]:
    out = dict(relic)
    kb = get_relic_info(relic.get("name", ""))
    if kb:
        out["kb"] = {
            "description": kb.get("description", ""),
            "rarity": kb.get("rarity", ""),
            "flavor_text": kb.get("flavor_text", ""),
        }
    else:
        out["kb"] = None
    return out


def enrich_potion(potion: dict[str, Any], game: dict[str, Any]) -> dict[str, Any]:
    out = dict(potion)
    kb = get_parsed_potion_info(
        potion.get("name", ""),
        has_sacred_bark=_has_sacred_bark(game),
    )
    if kb:
        out["kb"] = {"effect": kb.get("effect", "")}
    else:
        out["kb"] = None
    return out


def enrich_power(power: dict[str, Any]) -> dict[str, Any]:
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


def enrich_monster(monster: dict[str, Any]) -> dict[str, Any]:
    out = dict(monster)
    out["powers"] = [enrich_power(p) for p in out.get("powers", [])]
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


def monster_kb_public(name: str) -> dict[str, Any] | None:
    """Compact monster KB for map boss tooltip (matches legacy shape)."""
    kb = get_monster_info(name)
    if not kb:
        return None
    return {
        "hp_range": kb.get("hp") or "",
        "moves": kb.get("moves") or [],
        "notes": kb.get("notes") or "",
        "ai": kb.get("ai") or "",
    }
