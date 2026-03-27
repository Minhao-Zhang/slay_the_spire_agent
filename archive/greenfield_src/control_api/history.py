"""Read-only history API: trace events + LangGraph checkpoint timeline."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from langchain_core.runnables import RunnableConfig

from src.control_api import agent_runtime
from src.control_api.checkpoint_factory import checkpointer_mode, default_sqlite_path
from src.trace_telemetry.runtime import get_app_trace_store

router = APIRouter(tags=["history"])

CHECKPOINT_VALUES_MAX_BYTES = 512_000
_SAFE_STATE_VALUE_KEYS = frozenset(
    {
        "state_id",
        "view_model",
        "proposal",
        "emitted_command",
        "decision_trace",
        "failure_streak",
        "memory_log",
        "memory_seq_cursor",
        "shortcut_log",
        "combat_fingerprint",
        "command_queue",
    },
)


def _debug_history_allows_ingress() -> bool:
    v = os.environ.get("SLAY_DEBUG_HISTORY_STATE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _filter_checkpoint_values(values: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in _SAFE_STATE_VALUE_KEYS:
        if k not in values:
            continue
        out[k] = values[k]
    if _debug_history_allows_ingress() and "ingress_raw" in values:
        out["ingress_raw"] = values["ingress_raw"]
    elif "ingress_raw" in values:
        out["ingress_raw"] = {"redacted": True}
    mem = out.get("memory_log")
    if isinstance(mem, list) and len(mem) > 200:
        out["memory_log"] = mem[-200:]
        out["memory_log_truncated"] = True
    raw = json.dumps(out, default=str)
    if len(raw.encode("utf-8")) > CHECKPOINT_VALUES_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="checkpoint values exceed SLAY_HISTORY_CHECKPOINT_MAX_BYTES",
        )
    return out


def _distinct_sqlite_checkpoint_thread_ids() -> list[str]:
    if checkpointer_mode() != "sqlite":
        return []
    path = default_sqlite_path()
    try:
        conn = sqlite3.connect(path, check_same_thread=False)
    except OSError:
        return []
    try:
        cur = conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id IS NOT NULL",
        )
        return sorted({str(r[0]) for r in cur if r[0]})
    finally:
        conn.close()


def _snapshot_to_dict(snap: Any) -> dict[str, Any]:
    cfg = snap.config.get("configurable") or {}
    parent_cfg: dict[str, Any] | None = None
    if snap.parent_config and isinstance(snap.parent_config, dict):
        parent_cfg = snap.parent_config.get("configurable") or {}
    values = snap.values if isinstance(snap.values, dict) else {}
    interrupts = getattr(snap, "interrupts", ()) or ()
    interrupt_info: list[dict[str, Any]] = []
    for it in interrupts:
        if hasattr(it, "id"):
            interrupt_info.append({"id": getattr(it, "id", None)})
        else:
            interrupt_info.append({"repr": repr(it)})
    return {
        "checkpoint_id": cfg.get("checkpoint_id"),
        "checkpoint_ns": cfg.get("checkpoint_ns"),
        "parent_checkpoint_id": (parent_cfg or {}).get("checkpoint_id"),
        "created_at": snap.created_at,
        "state_id": values.get("state_id"),
        "next": list(snap.next) if snap.next else [],
        "metadata": snap.metadata,
        "interrupts": interrupt_info,
    }


@router.get("/api/history/threads")
def list_history_threads(
    merge_checkpoint_threads: bool = Query(
        False,
        description="Include thread_ids from SQLite checkpoints (no trace rows yet).",
    ),
) -> dict[str, Any]:
    threads = get_app_trace_store().list_thread_summaries()
    if not merge_checkpoint_threads:
        return {"threads": threads}
    by_tid: dict[str, dict[str, Any]] = {str(t["thread_id"]): dict(t) for t in threads}
    for tid in _distinct_sqlite_checkpoint_thread_ids():
        if tid not in by_tid:
            by_tid[tid] = {"thread_id": tid, "event_count": 0}
    merged = sorted(by_tid.values(), key=lambda x: str(x["thread_id"]))
    return {"threads": merged}


@router.get("/api/history/events")
def list_history_events(
    thread_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    ev = get_app_trace_store().list_events(
        thread_id=thread_id,
        limit=limit,
        offset=offset,
    )
    return {"events": ev, "count": len(ev)}


@router.get("/api/history/checkpoints")
def list_history_checkpoints(
    thread_id: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    g = agent_runtime.get_compiled_agent_graph()
    cfg: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    try:
        hist = g.get_state_history(cfg, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    checkpoints = [_snapshot_to_dict(s) for s in hist]
    return {"thread_id": thread_id, "checkpoints": checkpoints}


@router.get("/api/history/checkpoint")
def get_history_checkpoint(
    thread_id: str = Query(..., min_length=1),
    checkpoint_id: str | None = Query(
        None,
        description="Optional; latest checkpoint for thread when omitted.",
    ),
    checkpoint_ns: str = Query(""),
) -> dict[str, Any]:
    g = agent_runtime.get_compiled_agent_graph()
    conf: dict[str, Any] = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}
    if checkpoint_id:
        conf["checkpoint_id"] = checkpoint_id
    cfg: RunnableConfig = {"configurable": conf}
    try:
        snap = g.get_state(cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if snap is None:
        raise HTTPException(status_code=404, detail="no checkpoint for thread/config")
    meta = _snapshot_to_dict(snap)
    values = snap.values if isinstance(snap.values, dict) else {}
    try:
        meta["values"] = _filter_checkpoint_values(values)
    except HTTPException:
        raise
    return {"thread_id": thread_id, "checkpoint": meta}
