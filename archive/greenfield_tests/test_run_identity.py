from __future__ import annotations

import pytest

from src.domain.run_identity import (
    MENU_RUN_SEED,
    MENU_THREAD_ID,
    extract_run_seed_and_thread_id,
)


def test_menu_when_not_in_game() -> None:
    run_seed, tid = extract_run_seed_and_thread_id(
        {"in_game": False, "game_state": {"seed": 123}},
    )
    assert run_seed == MENU_RUN_SEED
    assert tid == MENU_THREAD_ID


def test_run_from_numeric_seed() -> None:
    run_seed, tid = extract_run_seed_and_thread_id(
        {
            "in_game": True,
            "game_state": {"seed": 7836656617071767246},
        },
    )
    assert run_seed == "7836656617071767246"
    assert tid == "run-7836656617071767246"


def test_run_from_string_numeric_seed() -> None:
    run_seed, tid = extract_run_seed_and_thread_id(
        {"in_game": True, "game_state": {"seed": " 42 "}},
    )
    assert run_seed == "42"
    assert tid == "run-42"


def test_menu_when_in_game_but_seed_missing() -> None:
    run_seed, tid = extract_run_seed_and_thread_id(
        {"in_game": True, "game_state": {"floor": 1}},
    )
    assert run_seed == MENU_RUN_SEED
    assert tid == MENU_THREAD_ID


def test_state_wrapper() -> None:
    run_seed, tid = extract_run_seed_and_thread_id(
        {"state": {"in_game": True, "game_state": {"seed": 99}}},
    )
    assert run_seed == "99"
    assert tid == "run-99"


def test_bool_seed_treated_as_missing() -> None:
    run_seed, tid = extract_run_seed_and_thread_id(
        {"in_game": True, "game_state": {"seed": True}},
    )
    assert run_seed == MENU_RUN_SEED


@pytest.mark.parametrize(
    "source,expected",
    [
        ({"in_game": True, "game_state": {}}, (MENU_RUN_SEED, MENU_THREAD_ID)),
        (
            {"in_game": True, "game_state": {"seed": "abc_xyz"}},
            ("abc_xyz", "run-abc_xyz"),
        ),
    ],
)
def test_edge_cases(source: dict, expected: tuple[str, str]) -> None:
    assert extract_run_seed_and_thread_id(source) == expected
