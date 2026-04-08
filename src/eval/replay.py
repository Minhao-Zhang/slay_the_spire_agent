from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_run_dirs(logs_dir: Path, run_name: str | None) -> list[Path]:
    """Resolve runs under ``logs/games/<run>`` when present, else legacy ``logs/<run>``.

    When listing all runs, merge ``logs/games/*`` with top-level ``logs/*`` (excluding
    the ``games`` directory), preferring ``games`` when names collide.
    """
    logs_dir = logs_dir.resolve()
    games_root = logs_dir / "games"
    if run_name:
        for root in (games_root, logs_dir):
            if root == games_root and not root.is_dir():
                continue
            target = root / run_name
            if target.is_dir():
                return [target]
        return []
    merged: dict[str, Path] = {}
    if games_root.is_dir():
        for p in games_root.iterdir():
            if p.is_dir():
                merged[p.name] = p
    if logs_dir.is_dir():
        for p in logs_dir.iterdir():
            if p.is_dir() and p.name != "games":
                merged.setdefault(p.name, p)
    return sorted(merged.values(), key=lambda p: p.name, reverse=True)


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
        help="Path to logs root (default: logs). Runs are read from logs/games/<run> when that folder exists, else legacy logs/<run>.",
    )
    parser.add_argument(
        "--run",
        default="",
        help="Optional single run directory name under logs.",
    )
    args = parser.parse_args()

    logs_dir = Path(args.logs_dir).resolve()
    metrics = analyze_logs(logs_dir=logs_dir, run_name=args.run or None)
    print(json.dumps(_as_dict(metrics), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
