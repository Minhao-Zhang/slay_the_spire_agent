from __future__ import annotations

import pytest

from src.game_adapter.emit import validate_idle_command, validate_operator_command


def test_validate_operator_canonical() -> None:
    vm = {"actions": [{"command": "PLAY 1 0", "label": "x"}]}
    assert validate_operator_command(vm, "play  1 0") == "PLAY 1 0"


def test_validate_operator_rejects() -> None:
    vm = {"actions": [{"command": "END", "label": "e"}]}
    with pytest.raises(ValueError, match="not_legal"):
        validate_operator_command(vm, "NOPE")


def test_validate_idle_wait_and_state() -> None:
    st = {"available_commands": ["wait", "state"]}
    assert validate_idle_command(st, "wait 10") == "wait 10"
    assert validate_idle_command(st, "state") == "state"


def test_validate_idle_rejects() -> None:
    st = {"available_commands": ["end"]}
    with pytest.raises(ValueError):
        validate_idle_command(st, "wait 10")
