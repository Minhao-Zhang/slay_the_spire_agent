from __future__ import annotations

from src.decision_engine import shortcuts


def test_in_fight_when_combat_present() -> None:
    assert shortcuts.in_fight({"combat": {}})
    assert not shortcuts.in_fight({"combat": None})
    assert not shortcuts.in_fight(None)


def test_in_fight_false_when_combat_blob_but_combat_reward_screen() -> None:
    """Victory reward often keeps ``combat_state`` in the payload; still not turn combat."""
    assert not shortcuts.in_fight(
        {
            "combat": {"hand": [], "monsters": []},
            "screen": {"type": "COMBAT_REWARD", "content": {"rewards": []}},
        },
    )


def test_try_shortcut_requires_ready_for_command() -> None:
    vm = {"actions": [{"command": "CONFIRM"}]}
    assert shortcuts.try_deterministic_shortcut({}, vm) == (None, "")
    assert shortcuts.try_deterministic_shortcut({"ready_for_command": False}, vm) == (
        None,
        "",
    )


def test_combat_reward_gold_picks_legal_choose() -> None:
    vm = {
        "screen": {
            "type": "COMBAT_REWARD",
            "content": {
                "rewards": [{"reward_type": "GOLD", "choice_index": 1}],
            },
        },
        "actions": [
            {"command": "choose 0"},
            {"command": "choose 1"},
        ],
    }
    cmd, kind = shortcuts.try_deterministic_shortcut({"ready_for_command": True}, vm)
    assert cmd == "choose 1"
    assert kind == "combat_reward_gold"


def test_combat_reward_gold_falls_back_to_reward_list_index() -> None:
    vm = {
        "screen": {
            "type": "COMBAT_REWARD",
            "content": {
                "rewards": [
                    {"reward_type": "GOLD", "gold": 10},
                    {"reward_type": "CARD"},
                ],
            },
        },
        "actions": [
            {"command": "choose 0"},
            {"command": "choose 1"},
        ],
    }
    cmd, kind = shortcuts.try_deterministic_shortcut({"ready_for_command": True}, vm)
    assert cmd == "choose 0"
    assert kind == "combat_reward_gold"


def test_auto_confirm_when_only_confirm_and_cancel() -> None:
    vm = {
        "actions": [
            {"command": "CONFIRM"},
            {"command": "CANCEL"},
        ],
    }
    cmd, kind = shortcuts.try_deterministic_shortcut({"ready_for_command": True}, vm)
    assert cmd == "CONFIRM"
    assert kind == "auto_confirm"


def test_single_non_potion_action() -> None:
    vm = {"actions": [{"command": "DECK"}]}
    cmd, kind = shortcuts.try_deterministic_shortcut({"ready_for_command": True}, vm)
    assert cmd == "DECK"
    assert kind == "single_action"


def test_single_potion_labeled_non_combat_potion() -> None:
    vm = {"actions": [{"command": "POTION 0"}]}
    cmd, kind = shortcuts.try_deterministic_shortcut({"ready_for_command": True}, vm)
    assert cmd == "POTION 0"
    assert kind == "non_combat_potion"
