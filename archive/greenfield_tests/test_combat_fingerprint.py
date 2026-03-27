from __future__ import annotations

from src.domain.combat_fingerprint import combat_encounter_fingerprint


def test_no_combat_returns_none() -> None:
    assert combat_encounter_fingerprint(None) is None
    assert combat_encounter_fingerprint({}) is None
    assert combat_encounter_fingerprint({"combat": None}) is None


def test_fingerprint_sorted_monster_keys() -> None:
    vm = {
        "header": {"floor": "5"},
        "combat": {
            "monsters": [
                {"name": "B", "max_hp": 10, "is_gone": False},
                {"name": "A", "max_hp": 20, "is_gone": False},
            ],
        },
    }
    fp = combat_encounter_fingerprint(vm)
    assert fp == "5:A:20|B:10"


def test_skips_gone_monsters() -> None:
    vm = {
        "header": {"floor": "3"},
        "combat": {
            "monsters": [
                {"name": "Cultist", "max_hp": 48, "is_gone": True},
            ],
        },
    }
    assert combat_encounter_fingerprint(vm) == "3:empty"
