"""Record graph completions into a trace store."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig

from src.decision_engine.proposal_logic import graph_now
from src.trace_telemetry.runtime import (
    get_app_trace_store,
    trace_recording_enabled,
)
from src.trace_telemetry.schema import build_agent_step_event
from src.trace_telemetry.store import InMemoryTraceStore

StepKindLit = Literal["ingress", "resume"]


def _select_store(cfg: RunnableConfig, explicit: InMemoryTraceStore | None) -> InMemoryTraceStore | None:
    if explicit is not None:
        return explicit
    conf = cfg.get("configurable") or {}
    ts = conf.get("trace_store")
    if isinstance(ts, InMemoryTraceStore):
        return ts
    if trace_recording_enabled():
        return get_app_trace_store()
    return None


def record_agent_invocation(
    *,
    cfg: RunnableConfig,
    raw_out: dict[str, Any],
    summary: dict[str, Any],
    step_kind: StepKindLit,
    resume_kind: str | None = None,
    store: InMemoryTraceStore | None = None,
) -> None:
    st = _select_store(cfg, store)
    if st is None:
        return
    conf = cfg.get("configurable") or {}
    thread_id = str(conf.get("thread_id") or "default")
    step_seq = st.next_step_seq(thread_id)
    idem = conf.get("trace_idempotency_key")
    idem_s = str(idem).strip() if idem is not None and str(idem).strip() else None
    ts_logical = graph_now(cfg)
    state_id = raw_out.get("state_id")
    if state_id is not None:
        state_id = str(state_id)
    evt = build_agent_step_event(
        thread_id=thread_id,
        step_seq=step_seq,
        step_kind=step_kind,  # type: ignore[arg-type]
        ts_logical=ts_logical,
        state_id=state_id,
        summary=summary,
        resume_kind=resume_kind,
        idempotency_key=idem_s,
    )
    st.append(evt)
