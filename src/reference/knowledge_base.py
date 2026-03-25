"""Load processed Spire JSON datasets; same role as legacy ``archive/.../knowledge_base``."""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from src.repo_paths import REPO_ROOT

PROCESSED_DATA_DIR = REPO_ROOT / "data" / "processed"


class DataStore:
    def __init__(self) -> None:
        self.cards: Dict[str, dict] = {}
        self.relics: Dict[str, dict] = {}
        self.monsters: Dict[str, dict] = {}
        self.bosses: Dict[str, dict] = {}
        self.events: Dict[str, dict] = {}
        self.powers: Dict[str, dict] = {}
        self.potions: Dict[str, dict] = {}

        self.is_loaded = False

    def load_all(self) -> None:
        if self.is_loaded:
            return

        def _load_json_list(filename: str) -> List[dict]:
            path = PROCESSED_DATA_DIR / filename
            if not path.exists():
                return []
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        self.cards = {c["name"].lower(): c for c in _load_json_list("cards.json")}
        self.relics = {r["name"].lower(): r for r in _load_json_list("relics.json")}
        self.monsters = {m["name"].lower(): m for m in _load_json_list("monsters.json")}
        self.bosses = {b["name"].lower(): b for b in _load_json_list("bosses.json")}
        self.events = {e["name"].lower(): e for e in _load_json_list("events.json")}
        self.powers = {p["name"].lower(): p for p in _load_json_list("powers.json")}
        self.potions = {p["name"].lower(): p for p in _load_json_list("potions.json")}

        self.is_loaded = True


_store = DataStore()


def _ensure_loaded() -> None:
    if not _store.is_loaded:
        _store.load_all()


def get_card_info(name: str) -> Optional[dict]:
    """Retrieve details about a specific card by name."""
    _ensure_loaded()
    key = name.lower().replace("'", "").replace('"', "")

    if key in _store.cards:
        return _store.cards[key]

    for k, v in _store.cards.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    return None


def get_parsed_card_info(name: str, upgrades: int = 0) -> Optional[dict]:
    """Card info with description adjusted for upgrade count (legacy behavior)."""
    card = get_card_info(name)
    if not card:
        return None

    parsed_card = dict(card)
    is_upgraded = upgrades > 0

    if parsed_card["name"] == "Searing Blow":
        damage = 12 + int(upgrades * (upgrades + 7) / 2)
        parsed_card["description"] = (
            f"Deal {damage} damage. Can be Upgraded any number of times."
        )
        return parsed_card

    if is_upgraded and parsed_card.get("description_upgraded"):
        parsed_card["description"] = parsed_card["description_upgraded"]
        return parsed_card

    desc = parsed_card.get("description", "")
    if desc:
        pattern = r"(\d+)\s*\((\d+)\)"

        def replace_match(match: re.Match[str]) -> str:
            upgraded_val = match.group(2)
            base_val = match.group(1)
            return upgraded_val if is_upgraded else base_val

        parsed_card["description"] = re.sub(pattern, replace_match, desc)

    return parsed_card


def get_relic_info(name: str) -> Optional[dict]:
    _ensure_loaded()
    key = name.lower().replace("'", "")

    if key in _store.relics:
        return _store.relics[key]

    for k, v in _store.relics.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    return None


def get_monster_info(name: str) -> Optional[dict]:
    _ensure_loaded()
    key = name.lower().replace("'", "")

    if key in _store.bosses:
        return _store.bosses[key]

    if key in _store.monsters:
        return _store.monsters[key]

    for k, v in _store.bosses.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    for k, v in _store.monsters.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    return None


def get_event_info(name: str) -> Optional[dict]:
    _ensure_loaded()
    key = name.lower().replace("'", "")

    if key in _store.events:
        return _store.events[key]

    for k, v in _store.events.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    return None


def get_power_info(name: str) -> Optional[dict]:
    _ensure_loaded()
    key = name.lower().replace("'", "").replace('"', "")

    if key in _store.powers:
        return _store.powers[key]

    for k, v in _store.powers.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    return None


def get_potion_info(name: str) -> Optional[dict]:
    if not name or name == "Potion Slot":
        return None
    _ensure_loaded()
    key = name.lower().replace("'", "").replace('"', "")

    if key in _store.potions:
        return _store.potions[key]

    for k, v in _store.potions.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v

    return {"name": name, "effect": "No data available.", "rarity": "Unknown"}


def get_parsed_potion_info(
    name: str, has_sacred_bark: bool = False
) -> Optional[dict]:
    potion = get_potion_info(name)
    if not potion:
        return None

    parsed = dict(potion)
    effect = parsed.get("effect", "")

    if has_sacred_bark and parsed.get("effect_sacred_bark"):
        parsed["effect"] = parsed["effect_sacred_bark"]
        return parsed

    if effect:
        pattern = r"(\d+)\s*\((\d+)\)"

        def replace_match(match: re.Match[str]) -> str:
            sb_val = match.group(2)
            base_val = match.group(1)
            return sb_val if has_sacred_bark else base_val

        parsed["effect"] = re.sub(pattern, replace_match, effect)

    return parsed


__all__ = [
    "PROCESSED_DATA_DIR",
    "get_card_info",
    "get_event_info",
    "get_monster_info",
    "get_parsed_card_info",
    "get_parsed_potion_info",
    "get_potion_info",
    "get_power_info",
    "get_relic_info",
]
