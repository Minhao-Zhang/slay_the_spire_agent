"""Deterministic RunReport from a single game log directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.reflection.log_io import (
    iter_ai_json_paths,
    iter_frame_json_paths,
    load_run_end_snapshot,
    load_run_metrics_lines,
    read_json_dict,
)
from src.agent.reflection.report_types import DecisionRecord, RunReport
from src.agent.reflection.run_report_reduce import (
    decision_record_from_ai_dict,
    is_key_combat_context,
    reduce_path_deck_resources,
)


def _decision_from_ai_log(data: dict[str, Any], source_path: str) -> DecisionRecord:
    return decision_record_from_ai_dict(data, source_path=source_path)


class RunAnalyzer:
    @staticmethod
    def analyze(run_dir: Path) -> RunReport:
        run_dir = run_dir.resolve()
        decisions: list[DecisionRecord] = []
        tool_usage: dict[str, int] = {}
        total_tokens = 0
        latencies: list[int] = []
        valid_like = 0

        all_lesson_ids: set[str] = set()
        for path in iter_ai_json_paths(run_dir):
            data = read_json_dict(path)
            if not data:
                continue
            decisions.append(_decision_from_ai_log(data, str(path)))
            raw_ids = data.get("retrieved_lesson_ids")
            if isinstance(raw_ids, list):
                for x in raw_ids:
                    s = str(x).strip()
                    if s:
                        all_lesson_ids.add(s)
            for tn in data.get("tool_names") or []:
                if tn:
                    tool_usage[str(tn)] = tool_usage.get(str(tn), 0) + 1
            tt = data.get("total_tokens")
            if isinstance(tt, (int, float)):
                total_tokens += int(tt)
            lat = data.get("latency_ms")
            if isinstance(lat, (int, float)):
                latencies.append(int(lat))
            st = str(data.get("status") or "")
            if st in {"awaiting_approval", "executed"}:
                valid_like += 1

        metrics = load_run_metrics_lines(run_dir)
        last_run: dict[str, Any] = {}
        for rec in metrics:
            if rec.get("type") == "run_end" and isinstance(rec.get("derived"), dict):
                last_run = dict(rec["derived"])

        snapshot = load_run_end_snapshot(run_dir)
        derived: dict[str, Any] = {}
        if snapshot and isinstance(snapshot.get("derived"), dict):
            derived = dict(snapshot["derived"])

        timestamp = str(derived.get("recorded_at") or last_run.get("recorded_at") or "")
        seed = str(derived.get("seed") or "")
        character = str(derived.get("class") or "")
        asc_raw = derived.get("ascension_level", 0)
        try:
            ascension = int(asc_raw) if asc_raw is not None else 0
        except (TypeError, ValueError):
            ascension = 0
        victory = derived.get("victory")
        if not isinstance(victory, bool):
            victory = last_run.get("victory") if isinstance(last_run.get("victory"), bool) else None
        floor_reached = 0
        try:
            fr = derived.get("floor") or last_run.get("floor")
            if fr is not None:
                floor_reached = int(fr)
        except (TypeError, ValueError):
            floor_reached = 0
        score = 0
        try:
            sc = derived.get("score") or last_run.get("score")
            if sc is not None:
                score = int(sc)
        except (TypeError, ValueError):
            score = 0

        vm_seq: list[dict[str, Any]] = []
        for fp in iter_frame_json_paths(run_dir):
            env = read_json_dict(fp)
            if not env:
                continue
            vm_s = env.get("vm_summary")
            if isinstance(vm_s, dict):
                vm_seq.append(vm_s)
        path_summary, deck_changes, resource_snapshots = reduce_path_deck_resources(vm_seq)

        key_combats: list[dict[str, Any]] = []
        notable: list[dict[str, Any]] = []
        for d in decisions:
            if is_key_combat_context(d.turn_key, d.planner_summary) and len(key_combats) < 24:
                key_combats.append(
                    {
                        "state_id": d.state_id,
                        "turn_key": d.turn_key,
                        "final_decision": d.final_decision,
                        "planner_summary": d.planner_summary,
                    }
                )
            if d.tool_names and len(notable) < 30:
                notable.append(
                    {
                        "state_id": d.state_id,
                        "screen_hint": d.turn_key,
                        "tools": d.tool_names,
                        "final_decision": d.final_decision,
                    }
                )

        n_dec = len(decisions)
        valid_rate = (valid_like / n_dec) if n_dec else 0.0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

        incomplete = not bool(snapshot)
        cause = None
        if incomplete:
            cause = "no_run_end_snapshot"

        return RunReport(
            run_dir=str(run_dir),
            timestamp=timestamp,
            seed=seed,
            character=character,
            ascension=ascension,
            victory=victory,
            floor_reached=floor_reached,
            score=score,
            cause_of_death=cause,
            path_summary=path_summary,
            deck_changes=deck_changes,
            resource_snapshots=resource_snapshots,
            key_combats=key_combats,
            notable_decisions=notable,
            total_ai_decisions=n_dec,
            valid_rate=round(valid_rate, 4),
            total_tokens=total_tokens,
            avg_latency_ms=round(avg_lat, 2),
            tool_usage=tool_usage,
            decision_count=n_dec,
            decisions=decisions,
            run_end_derived=derived,
            run_metrics_line_count=len(metrics),
            last_run_end_derived=last_run,
            retrieved_lesson_ids=sorted(all_lesson_ids),
        )
