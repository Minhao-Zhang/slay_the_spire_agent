import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# Build paths assuming the data/processed directory is at the project root
# This module is in src/reference/ so root is two levels up.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"

class DataStore:
    def __init__(self):
        self.cards: Dict[str, dict] = {}
        self.relics: Dict[str, dict] = {}
        self.monsters: Dict[str, dict] = {}
        self.bosses: Dict[str, dict] = {}
        self.events: Dict[str, dict] = {}
        self.powers: Dict[str, dict] = {}
        
        self.is_loaded = False

    def load_all(self):
        if self.is_loaded:
            return
            
        def _load_json_list(filename: str) -> List[dict]:
            path = PROCESSED_DATA_DIR / filename
            if not path.exists():
                print(f"Warning: Data file {path} not found.")
                return []
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        self.cards = {c["name"].lower(): c for c in _load_json_list("cards.json")}
        self.relics = {r["name"].lower(): r for r in _load_json_list("relics.json")}
        self.monsters = {m["name"].lower(): m for m in _load_json_list("monsters.json")}
        self.bosses = {b["name"].lower(): b for b in _load_json_list("bosses.json")}
        self.events = {e["name"].lower(): e for e in _load_json_list("events.json")}
        self.powers = {p["name"].lower(): p for p in _load_json_list("powers.json")}
        
        self.is_loaded = True

# Global singleton
_store = DataStore()

def _ensure_loaded():
    if not _store.is_loaded:
        _store.load_all()

# --- Public API Functions ---

def get_card_info(name: str) -> Optional[dict]:
    """Retrieve details about a specific card by name."""
    _ensure_loaded()
    # Replace single quotes, sometimes names have apostrophes like "Ascender's Bane"
    key = name.lower().replace("'", "").replace('"', '')
    
    # Try direct match
    if key in _store.cards:
        return _store.cards[key]
        
    # Try partial match if exact fails
    for k, v in _store.cards.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v
            
    return None

import re

def get_parsed_card_info(name: str, upgrades: int = 0) -> Optional[dict]:
    """Retrieve details about a specific card by name, automatically parsing the 
    description string based on the number of times the card is upgraded.
    
    Handles the 'Base (Upgraded)' syntax, explicit description_upgraded strings, 
    and the special case of Searing Blow which scales infinitely.
    """
    card = get_card_info(name)
    if not card:
        return None
        
    parsed_card = dict(card)
    is_upgraded = upgrades > 0
    
    # Special case for Searing Blow (n * (n + 7) / 2 + 12 damage)
    if parsed_card["name"] == "Searing Blow":
        damage = 12 + int(upgrades * (upgrades + 7) / 2)
        parsed_card["description"] = f"Deal {damage} damage. Can be Upgraded any number of times."
        return parsed_card
    
    # Use explicit upgraded description if it has one
    if is_upgraded and parsed_card.get("description_upgraded"):
        parsed_card["description"] = parsed_card["description_upgraded"]
        return parsed_card
        
    desc = parsed_card.get("description", "")
    if desc:
        pattern = r'(\d+)\s*\((\d+)\)'
        
        def replace_match(match):
            base_val = match.group(1)
            upgraded_val = match.group(2)
            return upgraded_val if is_upgraded else base_val
            
        parsed_card["description"] = re.sub(pattern, replace_match, desc)
        
    return parsed_card

def get_relic_info(name: str) -> Optional[dict]:
    """Retrieve details about a specific relic by name."""
    _ensure_loaded()
    key = name.lower().replace("'", "")
    
    if key in _store.relics:
        return _store.relics[key]
        
    for k, v in _store.relics.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v
            
    return None

def get_monster_info(name: str) -> Optional[dict]:
    """Retrieve details about a specific monster (or boss) by name."""
    _ensure_loaded()
    key = name.lower().replace("'", "")
    
    if key in _store.bosses:
        return _store.bosses[key]
        
    if key in _store.monsters:
        return _store.monsters[key]
        
    # Fuzzy match bosses
    for k, v in _store.bosses.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v
            
    # Fuzzy match standard monsters
    for k, v in _store.monsters.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v
            
    return None

def get_event_info(name: str) -> Optional[dict]:
    """Retrieve details about a random event or shrine by name."""
    _ensure_loaded()
    key = name.lower().replace("'", "")
    
    if key in _store.events:
        return _store.events[key]
        
    for k, v in _store.events.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v
            
    return None

def get_power_info(name: str) -> Optional[dict]:
    """Retrieve details about a power (buff/debuff) by name."""
    _ensure_loaded()
    key = name.lower().replace("'", "").replace('"', '')
    
    if key in _store.powers:
        return _store.powers[key]
    
    for k, v in _store.powers.items():
        if key in k.replace("'", "") or k.replace("'", "") in key:
            return v
            
    return None

def get_potion_info(name: str) -> Optional[dict]:
    """Retrieve details about a potion by name.
    Returns a placeholder until a potions.json data file is added.
    """
    if not name or name == "Potion Slot":
        return None
    return {"name": name, "effect": "No data available.", "rarity": "Unknown"}
