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

_SAMPLE_FLOORS = frozenset({1, 6, 12, 17, 25, 33, 40, 50})
_COMBAT_KEYWORDS = (
    "boss",
    "heart",
    "donu",
    "deca",
    "elite",
    "champ",
    "collector",
    "automaton",
    "guardian",
    "awakened",
)


def _decision_from_ai_log(data: dict[str, Any], source_path: str) -> DecisionRecord:
    tools = data.get("tool_names")
    if not isinstance(tools, list):
        tools = []
    lr = data.get("lessons_retrieved", 0)
    if not isinstance(lr, int):
        try:
            lr = int(lr)
        except (TypeError, ValueError):
            lr = 0
    sr = data.get("strategist_ran")
    strategist_ran = bool(sr) if isinstance(sr, bool) else str(sr).lower() == "true"
    return DecisionRecord(
        state_id=str(data.get("state_id") or ""),
        turn_key=str(data.get("turn_key") or ""),
        status=str(data.get("status") or ""),
        final_decision=data.get("final_decision") if data.get("final_decision") is not None else None,
        planner_summary=str(data.get("planner_summary") or ""),
        llm_model_used=str(data.get("llm_model_used") or ""),
        reasoning_effort_used=str(data.get("reasoning_effort_used") or ""),
        strategist_ran=strategist_ran,
        lessons_retrieved=lr,
        tool_names=[str(t) for t in tools if t],
        source_path=source_path,
    )


def _is_key_combat_context(turn_key: str, planner_summary: str) -> bool:
    blob = f"{turn_key} {planner_summary}".lower()
    return any(k in blob for k in _COMBAT_KEYWORDS) or "combat" in blob


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

        path_summary: list[str] = []
        deck_changes: list[dict[str, Any]] = []
        resource_snapshots: list[dict[str, Any]] = []
        prev_deck: int | None = None
        prev_screen = ""
        seen_floors_sample: set[int] = set()

        for fp in iter_frame_json_paths(run_dir):
            env = read_json_dict(fp)
            if not env:
                continue
            vm_s = env.get("vm_summary")
            if not isinstance(vm_s, dict):
                continue
            floor = vm_s.get("floor")
            fl_int: int | None
            try:
                fl_int = int(floor) if floor is not None else None
            except (TypeError, ValueError):
                fl_int = None
            stype = str(vm_s.get("screen_type") or "NONE").upper()
            if fl_int is not None:
                path_summary.append(f"floor {fl_int} {stype}")
                if fl_int in _SAMPLE_FLOORS and fl_int not in seen_floors_sample:
                    seen_floors_sample.add(fl_int)
                    resource_snapshots.append(
                        {
                            "floor": fl_int,
                            "hp": vm_s.get("current_hp"),
                            "max_hp": vm_s.get("max_hp"),
                            "gold": vm_s.get("gold"),
                            "deck_size": vm_s.get("deck_size"),
                            "relic_count": vm_s.get("relic_count"),
                        }
                    )
            ds = vm_s.get("deck_size")
            try:
                ds_int = int(ds) if ds is not None else None
            except (TypeError, ValueError):
                ds_int = None
            if prev_deck is not None and ds_int is not None and ds_int != prev_deck:
                action = "deck_size_change"
                if stype == "COMBAT_REWARD" or prev_screen == "COMBAT_REWARD":
                    action = "possible_card_pick"
                deck_changes.append(
                    {
                        "floor": fl_int,
                        "action": action,
                        "from": prev_deck,
                        "to": ds_int,
                        "screen": stype,
                    }
                )
            if ds_int is not None:
                prev_deck = ds_int
            prev_screen = stype

        if len(path_summary) > 80:
            path_summary = path_summary[:40] + [f"... ({len(path_summary) - 80} more) ..."] + path_summary[-40:]

        key_combats: list[dict[str, Any]] = []
        notable: list[dict[str, Any]] = []
        for d in decisions:
            if _is_key_combat_context(d.turn_key, d.planner_summary) and len(key_combats) < 24:
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
