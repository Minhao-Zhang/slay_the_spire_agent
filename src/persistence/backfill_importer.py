"""Import historical ``logs/games/<run>`` into Phase 0 SQL tables (Phase 1)."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import uuid
from pathlib import Path
from typing import Any

from src.agent.reflection.log_io import (
    ai_sidecar_event_index,
    iter_ai_json_paths,
    iter_frame_json_paths,
    load_run_end_snapshot,
    load_run_metrics_lines,
    read_json_dict,
)
from src.persistence.backfill_constants import (
    BF_STAGE_DECISIONS,
    BF_STAGE_DONE,
    BF_STAGE_FRAMES,
    BF_STAGE_LLM_CALLS,
    BF_STAGE_RUN_END,
    BF_STAGE_RUNS,
    BF_STATUS_FAILED,
    BF_STATUS_PENDING,
    BF_STATUS_RUNNING,
    BF_STATUS_SUCCEEDED,
)
from src.persistence.models import BackfillJobRow
from src.persistence.sql_repository import SqlRepository, append_mutation_event_to_session

_BACKFILL_EXP_ID = "phase1-backfill-exp"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _engine_label(repo: SqlRepository) -> str:
    with repo._session() as s:
        name = s.bind.dialect.name if s.bind else "sqlite"
    return "postgres" if name == "postgresql" else "sqlite"


def _run_end_payload_from_disk(game_dir: Path) -> dict[str, Any] | None:
    snap = load_run_end_snapshot(game_dir)
    if snap and isinstance(snap.get("derived"), dict):
        d = dict(snap["derived"])
        return {
            "state_id": str(snap.get("state_id") or d.get("state_id") or ""),
            "victory": d.get("victory"),
            "score": d.get("score"),
            "screen_name": d.get("screen_name"),
            "floor": d.get("floor"),
            "act": d.get("act"),
            "gold": d.get("gold"),
            "current_hp": d.get("current_hp"),
            "max_hp": d.get("max_hp"),
            "deck_size": d.get("deck_size"),
            "relic_count": d.get("relic_count"),
            "potion_slots": d.get("potion_slots"),
            "recorded_at": str(d.get("recorded_at") or ""),
        }
    metrics = load_run_metrics_lines(game_dir)
    for rec in reversed(metrics):
        if rec.get("type") == "run_end" and isinstance(rec.get("derived"), dict):
            d = dict(rec["derived"])
            return {
                "state_id": str(rec.get("state_id") or ""),
                "victory": d.get("victory"),
                "score": d.get("score"),
                "screen_name": d.get("screen_name"),
                "floor": d.get("floor"),
                "act": d.get("act"),
                "gold": d.get("gold"),
                "current_hp": d.get("current_hp"),
                "max_hp": d.get("max_hp"),
                "deck_size": d.get("deck_size"),
                "relic_count": d.get("relic_count"),
                "potion_slots": d.get("potion_slots"),
                "recorded_at": str(d.get("recorded_at") or rec.get("timestamp") or ""),
            }
    return None


def backfill_run_directory(
    repo: SqlRepository,
    game_dir: Path,
    *,
    dry_run: bool = False,
    resume: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Import one run directory. Returns a small status dict."""
    game_dir = game_dir.resolve()
    run_key = game_dir.name
    if force:
        run_existing_for_force = repo.get_run_row_by_dir_name(run_key)
        if run_existing_for_force:
            repo.delete_run_cascade(run_existing_for_force.id)
        repo.delete_backfill_job_by_run_dir(run_key)
    job_existing = repo.get_backfill_job_by_run_dir(run_key)
    if job_existing and job_existing.status == BF_STATUS_SUCCEEDED and not force:
        return {"status": "skipped", "reason": "backfill_job_succeeded", "run_dir": run_key}
    if resume and job_existing and job_existing.status == BF_STATUS_FAILED:
        payload = job_existing.rows_written_json
        if isinstance(payload, dict) and payload.get("run_id"):
            repo.delete_run_cascade(str(payload["run_id"]))
        repo.delete_backfill_job_by_run_dir(run_key)
        job_existing = None
    run_existing = repo.get_run_row_by_dir_name(run_key)
    if run_existing and not force:
        return {"status": "skipped", "reason": "run_dir_name_exists", "run_dir": run_key}
    if not resume and job_existing and job_existing.status == BF_STATUS_FAILED:
        return {"status": "skipped", "reason": "failed_job_use_resume", "run_dir": run_key}

    frame_paths = iter_frame_json_paths(game_dir)
    if not frame_paths:
        return {"status": "skipped", "reason": "no_frame_json", "run_dir": run_key}

    if dry_run:
        return {
            "status": "dry_run",
            "run_dir": run_key,
            "frames": len(frame_paths),
            "ai_logs": len(iter_ai_json_paths(game_dir)),
        }

    job_id = str(uuid.uuid4())
    job = BackfillJobRow(
        id=job_id,
        run_dir=run_key,
        stage=BF_STAGE_RUNS,
        status=BF_STATUS_PENDING,
        started_at=_utcnow(),
        finished_at=None,
        error=None,
        rows_written_json=None,
    )
    repo.save_backfill_job(job)
    job.status = BF_STATUS_RUNNING
    repo.save_backfill_job(job)

    run_id = str(uuid.uuid4())
    snap = load_run_end_snapshot(game_dir)
    derived: dict[str, Any] = {}
    if snap and isinstance(snap.get("derived"), dict):
        derived = dict(snap["derived"])
    metrics = load_run_metrics_lines(game_dir)
    last_run: dict[str, Any] = {}
    for rec in metrics:
        if rec.get("type") == "run_end" and isinstance(rec.get("derived"), dict):
            last_run = dict(rec["derived"])

    seed = str(derived.get("seed") or last_run.get("seed") or "")
    character = str(derived.get("class") or last_run.get("class") or "")
    asc_raw = derived.get("ascension_level", last_run.get("ascension_level", 0))
    try:
        ascension = int(asc_raw) if asc_raw is not None else 0
    except (TypeError, ValueError):
        ascension = 0

    cfg_hash = hashlib.sha256(b"{}").hexdigest()
    create_payload: dict[str, Any] = {
        "run_id": run_id,
        "run_dir_name": run_key,
        "seed": seed,
        "character_class": character,
        "ascension_level": ascension,
        "storage_engine": _engine_label(repo),
        "system_prompt_hash": "0" * 64,
        "prompt_builder_version": "backfill-1",
        "reference_data_hash": None,
        "config_hash": cfg_hash,
        "knowledge_version_id": None,
        "experiment_id": _BACKFILL_EXP_ID,
        "experiment": {
            "id": _BACKFILL_EXP_ID,
            "name": "phase1-backfill",
            "decision_model": None,
            "reasoning_effort": None,
            "prompt_profile": "default",
            "config_hash": cfg_hash,
        },
        "source_log_path": str(game_dir),
        "langfuse_session_id": run_key,
        "status": "ended",
        "reflection_status": "skipped",
    }

    flush_every = max(1, int(os.getenv("BACKFILL_FLUSH_EVERY_N_FRAMES", "50")))
    audit = "migration"
    failure_stage = BF_STAGE_RUNS

    try:
        n_frames = 0
        n_ai = 0
        with repo.session_factory() as session:
            with session.begin():
                failure_stage = BF_STAGE_RUNS
                repo.create_run_in_session(session, create_payload)
                append_mutation_event_to_session(
                    session,
                    actor=audit,
                    target_kind="run",
                    target_id=run_id,
                    action="create_run",
                    before=None,
                    after={"run_dir_name": run_key},
                )

                failure_stage = BF_STAGE_FRAMES
                prev_floor: int | None = None
                for fp in frame_paths:
                    data = read_json_dict(fp)
                    if not data:
                        continue
                    try:
                        ei = int(fp.stem)
                    except ValueError:
                        continue
                    vm = data.get("vm_summary")
                    if not isinstance(vm, dict):
                        continue
                    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                    state_id = str(data.get("state_id") or "")
                    raw_floor = vm.get("floor")
                    fi: int | None = None
                    if isinstance(raw_floor, int):
                        fi = raw_floor
                    elif raw_floor is not None and str(raw_floor).strip() != "":
                        try:
                            fi = int(raw_floor)
                        except (TypeError, ValueError):
                            fi = None
                    act_val = vm.get("act")
                    act_i = act_val if isinstance(act_val, int) else None
                    is_floor_start = fi is not None and prev_floor is not None and fi != prev_floor
                    fid = str(uuid.uuid5(uuid.UUID(run_id), f"frame:{ei}"))
                    repo.insert_frame_in_session(
                        session,
                        {
                            "frame_id": fid,
                            "run_id": run_id,
                            "event_index": ei,
                            "state_id": state_id,
                            "screen_type": str(vm.get("screen_type") or "NONE"),
                            "floor": fi,
                            "act": act_i,
                            "turn_key": vm.get("turn_key"),
                            "ready_for_command": bool(meta.get("ready_for_command", False)),
                            "agent_mode": str(meta.get("agent_mode") or "manual"),
                            "ai_enabled": bool(meta.get("ai_enabled", False)),
                            "command_sent": meta.get("command_sent"),
                            "command_source": meta.get("command_source"),
                            "action": data.get("action"),
                            "is_floor_start": bool(is_floor_start),
                            "vm_summary": vm,
                            "meta": meta,
                            "state_projection": vm,
                        },
                    )
                    append_mutation_event_to_session(
                        session,
                        actor=audit,
                        target_kind="run_frame",
                        target_id=fid,
                        action="insert_frame",
                        before=None,
                        after={"run_id": run_id, "event_index": ei},
                    )
                    n_frames += 1
                    if fi is not None:
                        prev_floor = fi
                    if n_frames % flush_every == 0:
                        session.flush()

                failure_stage = BF_STAGE_DECISIONS
                for ai_path in iter_ai_json_paths(game_dir):
                    raw = read_json_dict(ai_path)
                    if not isinstance(raw, dict):
                        continue
                    ei = ai_sidecar_event_index(ai_path)
                    if ei is None:
                        continue
                    seq = raw.get("final_decision_sequence")
                    if not isinstance(seq, list):
                        seq = []
                    tools = raw.get("tool_names")
                    if not isinstance(tools, list):
                        tools = []
                    sr = raw.get("strategist_ran")
                    strategist_ran = bool(sr) if isinstance(sr, bool) else str(sr).lower() == "true"
                    dec_payload = {
                        "run_id": run_id,
                        "event_index": ei,
                        "state_id": str(raw.get("state_id") or ""),
                        "client_decision_id": str(raw.get("decision_id") or raw.get("state_id") or ""),
                        "turn_key": raw.get("turn_key"),
                        "status": str(raw.get("status") or "executed"),
                        "approval_status": str(raw.get("approval_status") or "approved"),
                        "execution_outcome": str(raw.get("execution_outcome") or ""),
                        "final_decision": raw.get("final_decision"),
                        "final_decision_sequence": [str(x) for x in seq if str(x).strip()],
                        "validation_error": str(raw.get("validation_error") or ""),
                        "error": str(raw.get("error") or ""),
                        "tool_names": [str(t) for t in tools if t],
                        "prompt_profile": str(raw.get("prompt_profile") or "default"),
                        "experiment_id": str(raw.get("experiment_id") or _BACKFILL_EXP_ID),
                        "experiment_tag": str(raw.get("experiment_tag") or ""),
                        "strategist_ran": strategist_ran,
                        "planner_ran": bool(raw.get("planner_ran", False)),
                        "react_ran": bool(raw.get("react_ran", False)),
                        "deck_size": raw.get("deck_size"),
                    }
                    decision_pk = repo.upsert_decision_final_in_session(session, dec_payload)
                    append_mutation_event_to_session(
                        session,
                        actor=audit,
                        target_kind="agent_decision",
                        target_id=decision_pk,
                        action="upsert_decision_final",
                        before=None,
                        after={"run_id": run_id, "event_index": ei},
                    )

                    failure_stage = BF_STAGE_LLM_CALLS
                    ltid = f"local-{uuid.uuid4()}"
                    loid = f"local-{uuid.uuid4()}"
                    call_id = str(uuid.uuid5(uuid.UUID(run_id), f"llm:{ei}"))
                    llm_payload = {
                        "id": call_id,
                        "run_id": run_id,
                        "frame_id": str(uuid.uuid5(uuid.UUID(run_id), f"frame:{ei}")),
                        "event_index": ei,
                        "state_id": str(raw.get("state_id") or ""),
                        "client_decision_id": str(raw.get("decision_id") or ""),
                        "turn_key": raw.get("turn_key"),
                        "stage": "decision",
                        "round_index": 1,
                        "model": raw.get("llm_model_used"),
                        "reasoning_effort": raw.get("reasoning_effort_used"),
                        "input_tokens": None,
                        "cached_input_tokens": None,
                        "uncached_input_tokens": None,
                        "output_tokens": None,
                        "reasoning_tokens": None,
                        "total_tokens": raw.get("total_tokens"),
                        "latency_ms": raw.get("latency_ms"),
                        "status": "ok",
                        "langfuse_trace_id": ltid,
                        "langfuse_observation_id": loid,
                        "prompt_profile": str(raw.get("prompt_profile") or "default"),
                    }
                    repo.record_llm_call_in_session(session, llm_payload)
                    append_mutation_event_to_session(
                        session,
                        actor=audit,
                        target_kind="llm_call",
                        target_id=call_id,
                        action="record_llm_call",
                        before=None,
                        after={"stage": "decision", "run_id": run_id},
                        langfuse_trace_id=ltid,
                    )
                    n_ai += 1

                failure_stage = BF_STAGE_RUN_END
                end_payload = _run_end_payload_from_disk(game_dir)
                if end_payload:
                    repo.upsert_run_end_in_session(session, {**end_payload, "run_id": run_id})
                    append_mutation_event_to_session(
                        session,
                        actor=audit,
                        target_kind="run_end",
                        target_id=run_id,
                        action="upsert_run_end",
                        before=None,
                        after={"run_id": run_id},
                    )

                append_mutation_event_to_session(
                    session,
                    actor=audit,
                    target_kind="backfill_job",
                    target_id=job_id,
                    action="backfill_run_directory",
                    before=None,
                    after={"run_id": run_id, "frames": n_frames, "ai_logs": n_ai},
                )

        job.stage = BF_STAGE_DONE
        job.status = BF_STATUS_SUCCEEDED
        job.finished_at = _utcnow()
        job.rows_written_json = {
            "run_id": run_id,
            "frames": n_frames,
            "ai_logs": n_ai,
            "stages_completed": [
                BF_STAGE_RUNS,
                BF_STAGE_FRAMES,
                BF_STAGE_DECISIONS,
                BF_STAGE_LLM_CALLS,
                BF_STAGE_RUN_END,
                BF_STAGE_DONE,
            ],
        }
        job.error = None
        repo.save_backfill_job(job)

        return {"status": "imported", "run_id": run_id, "run_dir": run_key, "frames": n_frames, "ai_logs": n_ai}
    except Exception as exc:  # noqa: BLE001
        job.stage = failure_stage
        job.status = BF_STATUS_FAILED
        job.finished_at = _utcnow()
        job.error = repr(exc)
        repo.save_backfill_job(job)
        raise
