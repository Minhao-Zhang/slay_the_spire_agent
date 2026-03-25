"""Read-only history API: trace events + LangGraph checkpoint timeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from langchain_core.runnables import RunnableConfig

from src.control_api import agent_runtime
from src.trace_telemetry.runtime import get_app_trace_store

router = APIRouter(tags=["history"])


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
def list_history_threads() -> dict[str, Any]:
    return {"threads": get_app_trace_store().list_thread_summaries()}


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
