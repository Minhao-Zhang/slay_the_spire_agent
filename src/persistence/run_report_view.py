"""Materialize :class:`RunReport` from SQL state (Phase 1) with optional disk sidecar merge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.agent.reflection.log_io import load_run_end_snapshot, load_run_metrics_lines, read_json_dict
from src.agent.reflection.report_types import DecisionRecord, RunReport
from src.agent.reflection.run_report_reduce import (
    decision_record_from_ai_dict,
    is_key_combat_context,
    reduce_path_deck_resources,
)
from src.persistence.models import AgentDecisionRow, RunEndRow, RunFrameRow, RunRow
from src.persistence.sql_repository import SqlRepository


def _decision_from_sql_row(row: AgentDecisionRow) -> DecisionRecord:
    tools = row.tool_names_json if isinstance(row.tool_names_json, list) else []
    return DecisionRecord(
        state_id=str(row.state_id or ""),
        turn_key=str(row.turn_key or ""),
        status=str(row.status or ""),
        final_decision=row.final_decision,
        planner_summary="",
        llm_model_used="",
        reasoning_effort_used="",
        strategist_ran=bool(row.strategist_ran),
        lessons_retrieved=0,
        tool_names=[str(t) for t in tools if t],
        source_path="",
    )


def _merge_sidecar(base: DecisionRecord, data: dict[str, Any], *, source_path: str) -> DecisionRecord:
    """Prefer rich fields from ``*.ai.json`` over SQL terminal snapshot."""
    sc = decision_record_from_ai_dict(data, source_path=source_path)
    return DecisionRecord(
        state_id=sc.state_id or base.state_id,
        turn_key=sc.turn_key or base.turn_key,
        status=sc.status or base.status,
        final_decision=sc.final_decision if sc.final_decision is not None else base.final_decision,
        planner_summary=sc.planner_summary or base.planner_summary,
        llm_model_used=sc.llm_model_used or base.llm_model_used,
        reasoning_effort_used=sc.reasoning_effort_used or base.reasoning_effort_used,
        strategist_ran=sc.strategist_ran if sc.planner_summary or sc.strategist_ran else base.strategist_ran,
        lessons_retrieved=sc.lessons_retrieved or base.lessons_retrieved,
        tool_names=sc.tool_names if sc.tool_names else base.tool_names,
        source_path=sc.source_path or base.source_path,
    )


def analyze_run_from_db(repo: SqlRepository, run_id: str) -> RunReport:
    """Build ``RunReport`` from ``runs`` / frames / decisions / ``llm_call`` / ``run_end``.

    When ``runs.source_log_path`` points at an existing log directory, ``*.ai.json`` sidecars
    are merged so ``RunReport`` matches :meth:`RunAnalyzer.analyze` for backfilled runs.
    """
    run_row = repo.get_run_row(run_id)
    if not run_row:
        raise ValueError(f"unknown run_id: {run_id}")

    frames: list[RunFrameRow] = repo.list_run_frames_ordered(run_id)
    vm_seq = [dict(f.vm_summary_json) if isinstance(f.vm_summary_json, dict) else {} for f in frames]
    path_summary, deck_changes, resource_snapshots = reduce_path_deck_resources(vm_seq)

    dec_rows: list[AgentDecisionRow] = repo.list_agent_decisions_ordered(run_id)
    log_root: Path | None = None
    if run_row.source_log_path:
        p = Path(run_row.source_log_path)
        if p.is_dir():
            log_root = p.resolve()

    decisions: list[DecisionRecord] = []
    tool_usage: dict[str, int] = {}
    total_tokens = 0
    latencies: list[int] = []
    valid_like = 0
    all_lesson_ids: set[str] = set()

    for row in dec_rows:
        base = _decision_from_sql_row(row)
        merged = base
        if log_root is not None:
            side = log_root / f"{int(row.event_index):04d}.ai.json"
            if side.is_file():
                raw = read_json_dict(side)
                if isinstance(raw, dict):
                    merged = _merge_sidecar(base, raw, source_path=str(side))
                    raw_ids = raw.get("retrieved_lesson_ids")
                    if isinstance(raw_ids, list):
                        for x in raw_ids:
                            s = str(x).strip()
                            if s:
                                all_lesson_ids.add(s)
                    tt = raw.get("total_tokens")
                    if isinstance(tt, (int, float)):
                        total_tokens += int(tt)
                    lat = raw.get("latency_ms")
                    if isinstance(lat, (int, float)):
                        latencies.append(int(lat))
        for tn in merged.tool_names:
            tool_usage[str(tn)] = tool_usage.get(str(tn), 0) + 1

        st = str(merged.status or "")
        if st in {"awaiting_approval", "executed"}:
            valid_like += 1
        decisions.append(merged)

    metrics_count = 0
    last_run: dict[str, Any] = {}
    derived: dict[str, Any] = {}
    snapshot_exists = False
    if log_root is not None:
        metrics = load_run_metrics_lines(log_root)
        metrics_count = len(metrics)
        for rec in metrics:
            if rec.get("type") == "run_end" and isinstance(rec.get("derived"), dict):
                last_run = dict(rec["derived"])
        snap = load_run_end_snapshot(log_root)
        if snap and isinstance(snap.get("derived"), dict):
            derived = dict(snap["derived"])
            snapshot_exists = True
    else:
        end_row = repo.get_run_end_for_run(run_id)
        if end_row:
            derived = _derived_from_run_end_row(end_row)
            last_run = dict(derived)
            snapshot_exists = True

    timestamp = str(derived.get("recorded_at") or last_run.get("recorded_at") or "")
    seed = str(derived.get("seed") or run_row.seed or "")
    character = str(derived.get("class") or run_row.character_class or "")
    asc_raw = derived.get("ascension_level", run_row.ascension_level)
    try:
        ascension = int(asc_raw) if asc_raw is not None else 0
    except (TypeError, ValueError):
        ascension = 0
    victory = derived.get("victory")
    if not isinstance(victory, bool) and isinstance(last_run.get("victory"), bool):
        victory = last_run.get("victory")
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

    if log_root is None:
        for call in repo.list_llm_calls_for_run(run_id):
            if call.latency_ms is not None:
                latencies.append(int(call.latency_ms))
            if call.total_tokens is not None:
                total_tokens += int(call.total_tokens)

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
    incomplete = log_root is not None and not snapshot_exists
    cause = "no_run_end_snapshot" if incomplete else None

    run_dir_display = run_row.run_dir_name or str(run_row.source_log_path or run_id)
    return RunReport(
        run_dir=str(log_root) if log_root else run_dir_display,
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
        run_metrics_line_count=metrics_count,
        last_run_end_derived=last_run,
        retrieved_lesson_ids=sorted(all_lesson_ids),
    )


def _derived_from_run_end_row(row: RunEndRow) -> dict[str, Any]:
    """Approximate ``run_end_snapshot`` ``derived`` from SQL columns only."""
    return {
        "victory": row.victory,
        "score": row.score,
        "floor": row.floor,
        "act": row.act,
        "gold": row.gold,
        "current_hp": row.current_hp,
        "max_hp": row.max_hp,
        "recorded_at": row.recorded_at or "",
    }
