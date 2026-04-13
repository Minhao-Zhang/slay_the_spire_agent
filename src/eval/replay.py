from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

from src.agent.reflection.log_io import (
    iter_ai_json_paths,
    read_json_dict,
    load_run_end_snapshot,
    load_run_metrics_lines,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_run_dirs(logs_dir: Path, run_name: str | None) -> list[Path]:
    """Resolve runs under ``logs/games/<run>`` only."""
    logs_dir = logs_dir.resolve()
    games_root = logs_dir / "games"
    if run_name:
        target = games_root / run_name
        return [target] if target.is_dir() else []
    if not games_root.is_dir():
        return []
    runs = [
        p
        for p in games_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    return sorted(runs, key=lambda p: p.name, reverse=True)


def _extract_tool_counts(ai_message: str) -> Counter:
    counter: Counter = Counter()
    if not ai_message:
        return counter
    for line in ai_message.splitlines():
        marker = "[Tool used:"
        idx = line.find(marker)
        if idx < 0:
            continue
        end = line.find("]", idx)
        if end < 0:
            continue
        name = line[idx + len(marker) : end].strip()
        if name:
            counter[name] += 1
    return counter


def _floor_from_logged_state(payload: dict[str, Any]) -> int | None:
    st = payload.get("state")
    if not isinstance(st, dict) or not st.get("in_game"):
        return None
    game = st.get("game_state") or {}
    f = game.get("floor")
    if isinstance(f, int):
        return f
    if isinstance(f, str) and f.strip().isdigit():
        return int(f.strip())
    return None


def _game_over_victory(payload: dict[str, Any]) -> tuple[bool, bool | None]:
    """Return (is_game_over, victory). victory is None if game over but flag missing."""
    st = payload.get("state")
    if not isinstance(st, dict):
        return False, None
    game = st.get("game_state") or {}
    if str(game.get("screen_type", "")).upper() != "GAME_OVER":
        return False, None
    ss = game.get("screen_state") or {}
    v = ss.get("victory")
    if isinstance(v, bool):
        return True, v
    return True, False


def summarize_run_directory(run_dir: Path) -> dict[str, Any]:
    """Per-run outcome: max floor seen while in-run, and terminal outcome if logged."""
    state_files = sorted(p for p in run_dir.glob("*.json") if not p.name.endswith(".ai.json"))
    max_floor: int | None = None
    saw_in_game = False
    completed = False
    victory: bool | None = None
    for path in state_files:
        payload = _read_json(path)
        if not payload:
            continue
        st = payload.get("state")
        if isinstance(st, dict) and st.get("in_game"):
            saw_in_game = True
        f = _floor_from_logged_state(payload)
        if f is not None:
            max_floor = f if max_floor is None else max(max_floor, f)
        go, v = _game_over_victory(payload)
        if go:
            completed = True
            victory = v if v is not None else False
    return {
        "run": run_dir.name,
        "saw_in_game": saw_in_game,
        "max_floor": max_floor,
        "run_completed": completed,
        "victory": victory,
    }


def wilson_score_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (clamped to [0, 1])."""
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _card_reward_action_from_sidecar(data: dict[str, Any]) -> str | None:
    tk = str(data.get("turn_key") or "")
    if not tk.upper().startswith("CARD_REWARD"):
        return None
    seq = data.get("final_decision_sequence")
    cmds: list[str] = []
    if isinstance(seq, list) and seq:
        cmds = [str(c).strip() for c in seq if str(c).strip()]
    else:
        fd = data.get("final_decision")
        if fd is not None:
            cmds = [str(fd).strip()]
    for raw in cmds:
        u = raw.upper()
        if u == "SKIP":
            return "skip"
        if u.startswith("CHOOSE"):
            return "take"
    return None


def _potion_used_from_sidecar(data: dict[str, Any]) -> bool:
    seq = data.get("final_decision_sequence")
    parts: list[str] = []
    seen: set[str] = set()
    if isinstance(seq, list):
        for c in seq:
            s = str(c).strip()
            if s and s not in seen:
                seen.add(s)
                parts.append(s)
    fd = data.get("final_decision")
    if fd is not None:
        s = str(fd).strip()
        if s and s not in seen:
            parts.append(s)
    for raw in parts:
        if raw.upper().startswith("POTION USE"):
            return True
    return False


def _combat_like_from_sidecar(data: dict[str, Any]) -> bool:
    tk = str(data.get("turn_key") or "").upper()
    return tk.startswith("COMBAT:")


def _aggregate_ai_decision_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_tokens = 0
    latency_samples: list[int] = []
    card_skip = 0
    card_take = 0
    potion_true = 0
    combat_like = 0
    last_deck: int | None = None
    decisions = 0
    for rec in records:
        decisions += 1
        tt = rec.get("total_tokens")
        if isinstance(tt, int):
            total_tokens += tt
        lat = rec.get("latency_ms")
        if isinstance(lat, int):
            latency_samples.append(lat)
        cra = rec.get("card_reward_action")
        if cra == "skip":
            card_skip += 1
        elif cra == "take":
            card_take += 1
        if rec.get("potion_used") is True:
            potion_true += 1
        st = str(rec.get("screen_type") or "").upper()
        if st == "COMBAT" or _combat_like_from_sidecar(rec):
            combat_like += 1
        ds = rec.get("deck_size")
        if isinstance(ds, int):
            last_deck = ds
    return {
        "decisions": decisions,
        "total_tokens": total_tokens,
        "latency_samples": latency_samples,
        "card_skip": card_skip,
        "card_take": card_take,
        "potion_true": potion_true,
        "combat_like": combat_like,
        "last_deck_size": last_deck,
    }


def _per_run_metrics_records(run_dir: Path) -> list[dict[str, Any]]:
    lines = load_run_metrics_lines(run_dir)
    return [r for r in lines if r.get("type") == "ai_decision"]


def _per_run_sidecar_records(run_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in iter_ai_json_paths(run_dir):
        data = read_json_dict(path)
        if not data:
            continue
        st = str(data.get("screen_type") or "").strip()
        if not st:
            tk = str(data.get("turn_key") or "")
            if ":" in tk:
                st = tk.split(":", 1)[0]
            else:
                st = ""
        cra = data.get("card_reward_action")
        if cra is None and st.upper() == "CARD_REWARD":
            cra = _card_reward_action_from_sidecar(data)
        pu = data.get("potion_used")
        if pu is None:
            pu = _potion_used_from_sidecar(data)
        row = {
            "type": "ai_decision",
            "total_tokens": data.get("total_tokens"),
            "latency_ms": data.get("latency_ms"),
            "card_reward_action": cra,
            "potion_used": pu,
            "screen_type": st or None,
            "deck_size": data.get("deck_size"),
            "turn_key": data.get("turn_key"),
        }
        out.append(row)
    return out


def _run_experiment_labels(run_dir: Path) -> tuple[str, str]:
    paths = iter_ai_json_paths(run_dir)
    if not paths:
        return "_unknown", ""
    data = read_json_dict(paths[0]) or {}
    eid = str(data.get("experiment_id") or "").strip() or "_unknown"
    tag = str(data.get("experiment_tag") or "").strip()
    return eid, tag


def _run_seed_victory_floor_deck(
    run_dir: Path, summary: dict[str, Any]
) -> tuple[str, bool | None, int | None, int | None]:
    """seed, victory, floor_reached, deck_at_end (best-effort)."""
    seed = ""
    victory = summary.get("victory")
    if isinstance(victory, bool):
        vic: bool | None = victory
    else:
        vic = None
    floor: int | None = summary.get("max_floor") if isinstance(summary.get("max_floor"), int) else None
    deck_end: int | None = None

    report_path = run_dir / "run_report.json"
    rep = read_json_dict(report_path)
    if rep:
        s = str(rep.get("seed") or "").strip()
        if s:
            seed = s
        vr = rep.get("victory")
        if isinstance(vr, bool):
            vic = vr
        fr = rep.get("floor_reached")
        if isinstance(fr, int):
            floor = fr

    snap = load_run_end_snapshot(run_dir)
    if snap and isinstance(snap.get("derived"), dict):
        d = snap["derived"]
        if not seed:
            seed = str(d.get("seed") or "").strip()
        if vic is None and isinstance(d.get("victory"), bool):
            vic = d["victory"]
        if floor is None:
            try:
                floor = int(d.get("floor")) if d.get("floor") is not None else None
            except (TypeError, ValueError):
                pass
        ds = d.get("deck_size")
        if isinstance(ds, int):
            deck_end = ds

    metrics_recs = _per_run_metrics_records(run_dir)
    agg_m = _aggregate_ai_decision_records(metrics_recs) if metrics_recs else None
    if agg_m and isinstance(agg_m.get("last_deck_size"), int):
        deck_end = agg_m["last_deck_size"]

    if not metrics_recs:
        side_recs = _per_run_sidecar_records(run_dir)
        agg_s = _aggregate_ai_decision_records(side_recs) if side_recs else None
        if agg_s and isinstance(agg_s.get("last_deck_size"), int):
            deck_end = agg_s["last_deck_size"]

    return seed, vic, floor, deck_end


def compare_experiments(logs_dir: Path) -> dict[str, Any]:
    """Group runs under ``logs/games/*`` by ``experiment_id``; aggregate evaluation metrics."""
    logs_dir = logs_dir.resolve()
    groups: dict[str, dict[str, Any]] = {}
    runs_out: list[dict[str, Any]] = []

    for run_dir in _iter_run_dirs(logs_dir, None):
        summary = summarize_run_directory(run_dir)
        eid, etag = _run_experiment_labels(run_dir)
        seed, vic, floor, deck_end = _run_seed_victory_floor_deck(run_dir, summary)

        metrics_recs = _per_run_metrics_records(run_dir)
        recs = metrics_recs if metrics_recs else _per_run_sidecar_records(run_dir)
        agg = _aggregate_ai_decision_records(recs)

        run_row = {
            "run": run_dir.name,
            "experiment_id": eid,
            "experiment_tag": etag,
            "seed": seed or None,
            "max_floor": floor,
            "victory": vic,
            "run_completed": summary.get("run_completed"),
            "deck_size_at_end": deck_end,
            "ai_decisions": agg["decisions"],
            "total_tokens": agg["total_tokens"],
            "avg_latency_ms": round(mean(agg["latency_samples"]), 2) if agg["latency_samples"] else None,
        }
        runs_out.append(run_row)

        if eid not in groups:
            groups[eid] = {
                "experiment_id": eid,
                "experiment_tags": Counter(),
                "runs": [],
                "wins": 0,
                "losses": 0,
                "completed": 0,
                "floors": [],
                "deck_ends": [],
                "tokens_per_run": [],
                "latencies": [],
                "card_skip": 0,
                "card_take": 0,
                "potion_true": 0,
                "combat_like": 0,
                "decisions": 0,
            }
        g = groups[eid]
        if etag:
            g["experiment_tags"][etag] += 1
        g["runs"].append(run_row)
        if summary.get("run_completed") and vic is True:
            g["wins"] += 1
            g["completed"] += 1
        elif summary.get("run_completed") and vic is False:
            g["losses"] += 1
            g["completed"] += 1
        if isinstance(floor, int):
            g["floors"].append(floor)
        if isinstance(deck_end, int):
            g["deck_ends"].append(deck_end)
        g["tokens_per_run"].append(agg["total_tokens"])
        g["latencies"].extend(agg["latency_samples"])
        g["card_skip"] += agg["card_skip"]
        g["card_take"] += agg["card_take"]
        g["potion_true"] += agg["potion_true"]
        g["combat_like"] += agg["combat_like"]
        g["decisions"] += agg["decisions"]

    grouped: dict[str, Any] = {}
    for eid, g in groups.items():
        done = g["wins"] + g["losses"]
        wr = (g["wins"] / done) if done else None
        lo, hi = wilson_score_interval(g["wins"], done) if done else (0.0, 0.0)
        cr_total = g["card_skip"] + g["card_take"]
        skip_rate = (g["card_skip"] / cr_total) if cr_total else None
        pot_denom = g["combat_like"] if g["combat_like"] > 0 else g["decisions"]
        pot_rate = (g["potion_true"] / pot_denom) if pot_denom else None
        n_runs = len(g["runs"])
        tag_common = g["experiment_tags"].most_common(1)
        tag_label = tag_common[0][0] if tag_common else ""
        grouped[eid] = {
            "experiment_id": eid,
            "experiment_tag": tag_label,
            "experiment_tags": dict(g["experiment_tags"]),
            "run_count": n_runs,
            "completed_runs": g["completed"],
            "wins": g["wins"],
            "losses": g["losses"],
            "win_rate": round(wr, 4) if wr is not None else None,
            "win_rate_wilson_95": [round(lo, 4), round(hi, 4)] if done else None,
            "avg_max_floor": round(mean(g["floors"]), 2) if g["floors"] else None,
            "avg_deck_size_at_end": round(mean(g["deck_ends"]), 2) if g["deck_ends"] else None,
            "avg_tokens_per_run": round(sum(g["tokens_per_run"]) / n_runs, 2) if n_runs else None,
            "avg_latency_per_decision_ms": round(mean(g["latencies"]), 2) if g["latencies"] else None,
            "card_reward_skip_rate": round(skip_rate, 4) if skip_rate is not None else None,
            "potion_use_rate": round(pot_rate, 4) if pot_rate is not None else None,
            "runs": g["runs"],
        }

    return {
        "logs_dir": str(logs_dir),
        "groups": dict(sorted(grouped.items(), key=lambda kv: kv[0])),
        "runs": sorted(runs_out, key=lambda r: r.get("run") or ""),
    }


def _sign_test_two_sided(plus: int, minus: int) -> float:
    """Two-sided binomial p-value for sign test (ties excluded), H0: p=0.5."""
    n = plus + minus
    if n == 0:
        return 1.0
    lo = min(plus, minus)

    def tail_cdf(k: int) -> float:
        s = 0.0
        for j in range(k + 1):
            s += math.comb(n, j) * (0.5**n)
        return s

    p_one = tail_cdf(lo)
    return min(1.0, 2.0 * p_one)


def seed_paired_comparison(logs_dir: Path, exp_a: str, exp_b: str) -> dict[str, Any]:
    """Match completed runs by seed across two experiment_ids; paired diffs and sign tests."""
    logs_dir = logs_dir.resolve()
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for run_dir in _iter_run_dirs(logs_dir, None):
        summary = summarize_run_directory(run_dir)
        eid, _etag = _run_experiment_labels(run_dir)
        seed, vic, floor, deck_end = _run_seed_victory_floor_deck(run_dir, summary)
        if not seed or eid not in (exp_a, exp_b):
            continue
        if not summary.get("run_completed"):
            continue
        by_key[(seed, eid)].append(
            {
                "run": run_dir.name,
                "seed": seed,
                "experiment_id": eid,
                "victory": vic,
                "max_floor": floor,
                "deck_size_at_end": deck_end,
            }
        )

    seeds_a = {s for (s, e) in by_key if e == exp_a}
    seeds_b = {s for (s, e) in by_key if e == exp_b}
    common = sorted(seeds_a & seeds_b)

    pairs: list[dict[str, Any]] = []
    floor_diffs: list[int] = []
    floor_plus = floor_minus = 0
    v_plus = v_minus = 0
    deck_diffs: list[int] = []
    deck_plus = deck_minus = 0

    for seed in common:
        ra = sorted(by_key[(seed, exp_a)], key=lambda x: x["run"])[0]
        rb = sorted(by_key[(seed, exp_b)], key=lambda x: x["run"])[0]
        pairs.append({"seed": seed, "a": ra, "b": rb})
        fa, fb = ra.get("max_floor"), rb.get("max_floor")
        if isinstance(fa, int) and isinstance(fb, int):
            floor_diffs.append(fa - fb)
            if fa > fb:
                floor_plus += 1
            elif fa < fb:
                floor_minus += 1
        va = ra.get("victory") is True
        vb = rb.get("victory") is True
        if va and not vb:
            v_plus += 1
        elif vb and not va:
            v_minus += 1
        da, db = ra.get("deck_size_at_end"), rb.get("deck_size_at_end")
        if isinstance(da, int) and isinstance(db, int):
            deck_diffs.append(da - db)
            if da > db:
                deck_plus += 1
            elif da < db:
                deck_minus += 1

    return {
        "experiment_a": exp_a,
        "experiment_b": exp_b,
        "paired_seeds": len(common),
        "pairs": pairs,
        "victory": {
            "a_wins_b_loses": v_plus,
            "b_wins_a_loses": v_minus,
            "sign_test_p_value": _sign_test_two_sided(v_plus, v_minus),
        },
        "max_floor": {
            "a_higher_count": floor_plus,
            "b_higher_count": floor_minus,
            "sign_test_p_value": _sign_test_two_sided(floor_plus, floor_minus),
            "mean_diff_a_minus_b": round(mean(floor_diffs), 4) if floor_diffs else None,
        },
        "deck_size_at_end": {
            "a_larger_count": deck_plus,
            "b_larger_count": deck_minus,
            "sign_test_p_value": _sign_test_two_sided(deck_plus, deck_minus),
            "mean_diff_a_minus_b": round(mean(deck_diffs), 4) if deck_diffs else None,
        },
    }


def _empty_group_stats() -> dict[str, int]:
    return {
        "legal_decisions": 0,
        "invalid_decisions": 0,
        "error_decisions": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "latency_samples": 0,
        "latency_sum_ms": 0,
    }


@dataclass
class ReplayMetrics:
    runs_scanned: int = 0
    state_logs: int = 0
    ai_logs: int = 0
    ready_for_command_states: int = 0
    ai_command_executions: int = 0
    ai_command_failures: int = 0
    legal_decisions: int = 0
    invalid_decisions: int = 0
    error_decisions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    tool_usage: dict[str, int] | None = None
    status_counts: dict[str, int] | None = None
    # Run-level outcomes (from raw state logs, not sidecars)
    runs_with_game_state: int = 0
    runs_completed: int = 0
    runs_incomplete: int = 0
    victories: int = 0
    defeats: int = 0
    avg_max_floor: float = 0.0
    max_floor_observed: int = 0
    run_summaries: list[dict[str, Any]] = field(default_factory=list)
    by_prompt_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_llm_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def legal_action_rate(self) -> float:
        total = self.legal_decisions + self.invalid_decisions + self.error_decisions
        return (self.legal_decisions / total) if total else 0.0

    @property
    def invalid_output_rate(self) -> float:
        total = self.legal_decisions + self.invalid_decisions + self.error_decisions
        return (self.invalid_decisions / total) if total else 0.0

    @property
    def ai_execution_success_rate(self) -> float:
        if self.ai_command_executions == 0:
            return 0.0
        return (self.ai_command_executions - self.ai_command_failures) / self.ai_command_executions

    @property
    def win_rate(self) -> float:
        done = self.victories + self.defeats
        return (self.victories / done) if done else 0.0


def analyze_logs(logs_dir: Path, run_name: str | None = None) -> ReplayMetrics:
    metrics = ReplayMetrics(tool_usage={}, status_counts={})
    latencies: list[int] = []
    tool_counts: Counter = Counter()
    status_counts: Counter = Counter()
    profile_stats: dict[str, dict[str, int]] = defaultdict(_empty_group_stats)
    model_stats: dict[str, dict[str, int]] = defaultdict(_empty_group_stats)
    max_floors_per_run: list[int] = []

    if not logs_dir.exists() or not logs_dir.is_dir():
        return metrics

    for run_dir in _iter_run_dirs(logs_dir, run_name):
        metrics.runs_scanned += 1
        summary = summarize_run_directory(run_dir)
        metrics.run_summaries.append(summary)
        if summary.get("saw_in_game"):
            metrics.runs_with_game_state += 1
        mf = summary.get("max_floor")
        if isinstance(mf, int):
            max_floors_per_run.append(mf)
            metrics.max_floor_observed = max(metrics.max_floor_observed, mf)
        if summary.get("run_completed"):
            metrics.runs_completed += 1
            if summary.get("victory") is True:
                metrics.victories += 1
            else:
                metrics.defeats += 1
        elif summary.get("saw_in_game"):
            metrics.runs_incomplete += 1

        state_files = sorted(run_dir.glob("*.json"))
        for state_path in state_files:
            if state_path.name.endswith(".ai.json"):
                continue
            state_payload = _read_json(state_path)
            if not state_payload:
                continue
            metrics.state_logs += 1
            meta = state_payload.get("meta", {}) or {}
            if bool(meta.get("ready_for_command")):
                metrics.ready_for_command_states += 1
            source = str(meta.get("command_source", ""))
            if source.startswith("ai"):
                metrics.ai_command_executions += 1
            state_error = str((state_payload.get("state") or {}).get("error", "")).strip()
            if source.startswith("ai") and state_error:
                metrics.ai_command_failures += 1

            ai_sidecar = state_path.with_suffix(".ai.json")
            if not ai_sidecar.exists():
                continue
            ai_payload = _read_json(ai_sidecar)
            if not ai_payload:
                continue
            metrics.ai_logs += 1

            status = str(ai_payload.get("status", "")).strip()
            if status:
                status_counts[status] += 1
            if status in {"awaiting_approval", "approved", "executed"}:
                metrics.legal_decisions += 1
                dec_bucket = "legal_decisions"
            elif status == "invalid":
                metrics.invalid_decisions += 1
                dec_bucket = "invalid_decisions"
            elif status in {"error", "disabled"}:
                metrics.error_decisions += 1
                dec_bucket = "error_decisions"
            else:
                dec_bucket = ""

            input_tokens = ai_payload.get("input_tokens")
            output_tokens = ai_payload.get("output_tokens")
            total_tokens = ai_payload.get("total_tokens")
            if isinstance(input_tokens, int):
                metrics.total_input_tokens += input_tokens
            if isinstance(output_tokens, int):
                metrics.total_output_tokens += output_tokens
            if isinstance(total_tokens, int):
                metrics.total_tokens += total_tokens

            latency_ms = ai_payload.get("latency_ms")
            lat_int: int | None = None
            if isinstance(latency_ms, int):
                latencies.append(latency_ms)
                lat_int = latency_ms

            profile_key = str(ai_payload.get("prompt_profile") or "_unset").strip() or "_unset"
            model_key = str(ai_payload.get("llm_model_used") or "_unset").strip() or "_unset"

            if dec_bucket:
                profile_stats[profile_key][dec_bucket] += 1
                model_stats[model_key][dec_bucket] += 1
            if isinstance(input_tokens, int):
                profile_stats[profile_key]["total_input_tokens"] += input_tokens
                model_stats[model_key]["total_input_tokens"] += input_tokens
            if isinstance(output_tokens, int):
                profile_stats[profile_key]["total_output_tokens"] += output_tokens
                model_stats[model_key]["total_output_tokens"] += output_tokens
            if isinstance(total_tokens, int):
                profile_stats[profile_key]["total_tokens"] += total_tokens
                model_stats[model_key]["total_tokens"] += total_tokens
            if lat_int is not None:
                profile_stats[profile_key]["latency_samples"] += 1
                profile_stats[profile_key]["latency_sum_ms"] += lat_int
                model_stats[model_key]["latency_samples"] += 1
                model_stats[model_key]["latency_sum_ms"] += lat_int

            tool_names = ai_payload.get("tool_names")
            if isinstance(tool_names, list):
                tool_counts.update([str(name) for name in tool_names if str(name).strip()])
            else:
                tool_counts.update(_extract_tool_counts(str(ai_payload.get("assistant_message", ""))))

    if latencies:
        ordered = sorted(latencies)
        metrics.avg_latency_ms = round(mean(ordered), 2)
        p95_index = max(0, min(len(ordered) - 1, int(0.95 * (len(ordered) - 1))))
        metrics.p95_latency_ms = float(ordered[p95_index])

    if max_floors_per_run:
        metrics.avg_max_floor = round(mean(max_floors_per_run), 2)

    metrics.tool_usage = dict(tool_counts)
    metrics.status_counts = dict(status_counts)

    def _finalize_groups(raw: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, st in raw.items():
            total_dec = st["legal_decisions"] + st["invalid_decisions"] + st["error_decisions"]
            legal_rate = (st["legal_decisions"] / total_dec) if total_dec else 0.0
            n_lat = st["latency_samples"]
            avg_lat = round(st["latency_sum_ms"] / n_lat, 2) if n_lat else 0.0
            out[key] = {
                "legal_decisions": st["legal_decisions"],
                "invalid_decisions": st["invalid_decisions"],
                "error_decisions": st["error_decisions"],
                "legal_action_rate": round(legal_rate, 4),
                "total_input_tokens": st["total_input_tokens"],
                "total_output_tokens": st["total_output_tokens"],
                "total_tokens": st["total_tokens"],
                "avg_latency_ms": avg_lat,
            }
        return dict(sorted(out.items()))

    metrics.by_prompt_profile = _finalize_groups(profile_stats)
    metrics.by_llm_model = _finalize_groups(model_stats)
    return metrics


def _as_dict(metrics: ReplayMetrics) -> dict[str, Any]:
    return {
        "runs_scanned": metrics.runs_scanned,
        "state_logs": metrics.state_logs,
        "ai_logs": metrics.ai_logs,
        "ready_for_command_states": metrics.ready_for_command_states,
        "ai_command_executions": metrics.ai_command_executions,
        "ai_command_failures": metrics.ai_command_failures,
        "ai_execution_success_rate": round(metrics.ai_execution_success_rate, 4),
        "legal_decisions": metrics.legal_decisions,
        "invalid_decisions": metrics.invalid_decisions,
        "error_decisions": metrics.error_decisions,
        "legal_action_rate": round(metrics.legal_action_rate, 4),
        "invalid_output_rate": round(metrics.invalid_output_rate, 4),
        "avg_latency_ms": metrics.avg_latency_ms,
        "p95_latency_ms": metrics.p95_latency_ms,
        "total_input_tokens": metrics.total_input_tokens,
        "total_output_tokens": metrics.total_output_tokens,
        "total_tokens": metrics.total_tokens,
        "status_counts": metrics.status_counts or {},
        "tool_usage": metrics.tool_usage or {},
        "run_outcomes": {
            "runs_with_in_game_states": metrics.runs_with_game_state,
            "runs_completed_game_over": metrics.runs_completed,
            "runs_incomplete_no_game_over": metrics.runs_incomplete,
            "victories": metrics.victories,
            "defeats": metrics.defeats,
            "win_rate": round(metrics.win_rate, 4),
            "avg_max_floor": metrics.avg_max_floor,
            "max_floor_observed": metrics.max_floor_observed,
        },
        "run_summaries": metrics.run_summaries,
        "by_prompt_profile": metrics.by_prompt_profile,
        "by_llm_model": metrics.by_llm_model,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay evaluator for Slay the Spire agent logs.",
    )
    parser.add_argument(
        "--logs-dir",
        default="logs",
        help="Path to logs root (default: logs). Runs are read from logs/games/<run>.",
    )
    parser.add_argument(
        "--run",
        default="",
        help="Optional single run directory name under logs.",
    )
    parser.add_argument(
        "--compare-experiments",
        action="store_true",
        help="Group runs by experiment_id and print aggregate metrics JSON.",
    )
    parser.add_argument(
        "--paired",
        nargs=2,
        metavar=("EXP_A", "EXP_B"),
        help="Paired comparison by seed for two experiment_id values.",
    )
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir).resolve()
    if args.compare_experiments:
        print(json.dumps(compare_experiments(logs_dir), indent=2))
        return 0
    if args.paired:
        print(json.dumps(seed_paired_comparison(logs_dir, args.paired[0], args.paired[1]), indent=2))
        return 0
    metrics = analyze_logs(logs_dir=logs_dir, run_name=args.run or None)
    print(json.dumps(_as_dict(metrics), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
