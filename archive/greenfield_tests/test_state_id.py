from __future__ import annotations

from src.domain.contracts.ingress import GameAdapterInput
from src.domain.contracts.state_id import compute_state_id


def test_state_id_stable_under_key_reorder() -> None:
    a = GameAdapterInput(
        in_game=True,
        ready_for_command=True,
        available_commands=["end"],
        game_state={"z": 1, "a": {"m": 2, "n": 3}},
    )
    b = GameAdapterInput(
        in_game=True,
        ready_for_command=True,
        available_commands=["end"],
        game_state={"a": {"n": 3, "m": 2}, "z": 1},
    )
    assert compute_state_id(a) == compute_state_id(b)


def test_state_id_changes_when_gameplay_differs() -> None:
    a = GameAdapterInput(
        in_game=True,
        ready_for_command=True,
        available_commands=["end"],
        game_state={"hp": 10},
    )
    b = GameAdapterInput(
        in_game=True,
        ready_for_command=True,
        available_commands=["end"],
        game_state={"hp": 11},
    )
    assert compute_state_id(a) != compute_state_id(b)


def test_state_id_ignores_extra_top_level_keys_in_raw_parse() -> None:
    """Ingress model drops unknown keys; hashing uses model_dump fingerprint only."""
    raw = {
        "in_game": True,
        "ready_for_command": True,
        "available_commands": [],
        "game_state": {},
        "telemetry_seq": 999,
    }
    g1 = GameAdapterInput.model_validate(raw)
    raw2 = {**raw, "telemetry_seq": 1000}
    g2 = GameAdapterInput.model_validate(raw2)
    assert compute_state_id(g1) == compute_state_id(g2)
