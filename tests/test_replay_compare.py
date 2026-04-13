from __future__ import annotations

import json
from pathlib import Path

from src.eval.replay import (
    compare_experiments,
    seed_paired_comparison,
    wilson_score_interval,
)


def _write(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_wilson_score_interval_bounds() -> None:
    lo, hi = wilson_score_interval(1, 4)
    assert 0 <= lo <= hi <= 1
    lo0, hi0 = wilson_score_interval(0, 0)
    assert lo0 == 0 and hi0 == 0


def test_compare_experiments_groups_by_experiment_id(tmp_path: Path) -> None:
    games = tmp_path / "games" / "run_one"
    games.mkdir(parents=True)
    _write(
        games / "0.json",
        {
            "state": {
                "in_game": True,
                "game_state": {
                    "screen_type": "GAME_OVER",
                    "screen_state": {"victory": True},
                    "floor": 18,
                },
            }
        },
    )
    _write(
        games / "0.ai.json",
        {
            "experiment_id": "abc123",
            "experiment_tag": "smoke",
            "turn_key": "MAP:1",
            "status": "executed",
            "total_tokens": 100,
            "latency_ms": 50,
            "deck_size": 15,
        },
    )
    metrics = games / "run_metrics.ndjson"
    metrics.write_text(
        json.dumps(
            {
                "type": "ai_decision",
                "total_tokens": 100,
                "latency_ms": 50,
                "screen_type": "CARD_REWARD",
                "deck_size": 15,
                "card_reward_action": "skip",
                "potion_used": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write(
        games / "run_report.json",
        {"seed": "99", "victory": True, "floor_reached": 18},
    )

    out = compare_experiments(tmp_path)
    assert "abc123" in out["groups"]
    g = out["groups"]["abc123"]
    assert g["run_count"] == 1
    assert g["wins"] == 1
    assert g["card_reward_skip_rate"] == 1.0


def test_seed_paired_comparison(tmp_path: Path) -> None:
    def make_run(name: str, exp: str, floor: int, vic: bool, seed: str) -> None:
        rd = tmp_path / "games" / name
        rd.mkdir(parents=True)
        _write(
            rd / "0.json",
            {
                "state": {
                    "in_game": True,
                    "game_state": {
                        "screen_type": "GAME_OVER",
                        "screen_state": {"victory": vic},
                        "floor": floor,
                    },
                }
            },
        )
        _write(
            rd / "0.ai.json",
            {
                "experiment_id": exp,
                "experiment_tag": "",
                "turn_key": "MAP:1",
                "status": "executed",
                "deck_size": 12,
            },
        )
        _write(
            rd / "run_report.json",
            {"seed": seed, "victory": vic, "floor_reached": floor},
        )

    make_run("r_a", "expA", 20, True, "seedX")
    make_run("r_b", "expB", 15, False, "seedX")

    paired = seed_paired_comparison(tmp_path, "expA", "expB")
    assert paired["paired_seeds"] == 1
    assert paired["victory"]["a_wins_b_loses"] == 1
    assert paired["victory"]["b_wins_a_loses"] == 0
    assert paired["max_floor"]["mean_diff_a_minus_b"] == 5.0
