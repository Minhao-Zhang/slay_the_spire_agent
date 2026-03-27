"""Versioned trace event payloads (JSON-serializable)."""

from __future__ import annotations

from typing import Any, Literal

TRACE_SCHEMA_VERSION = 2

StepKind = Literal["ingress", "resume"]


def build_agent_step_event(
    *,
    thread_id: str,
    step_seq: int,
    step_kind: StepKind,
    ts_logical: float,
    state_id: str | None,
    summary: dict[str, Any],
    resume_kind: str | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    """One row per graph invocation from the control plane (ingress or resume)."""
    prop = summary.get("proposal")
    status = None
    if isinstance(prop, dict):
        status = prop.get("status")
    pending = summary.get("pending_approval")
    evt: dict[str, Any] = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "event_type": "agent_step",
        "thread_id": thread_id,
        "step_seq": step_seq,
        "step_kind": step_kind,
        "ts_logical": ts_logical,
        "state_id": state_id,
        "proposal_status": status,
        "emitted_command": summary.get("emitted_command"),
        "awaiting_interrupt": bool(summary.get("awaiting_interrupt")),
        "pending_interrupt_state_id": (
            pending.get("interrupt", {}).get("state_id")
            if isinstance(pending, dict) and isinstance(pending.get("interrupt"), dict)
            else None
        ),
        "decision_trace": list(summary.get("decision_trace") or []),
        "failure_streak": int(summary.get("failure_streak") or 0),
        "agent_error": summary.get("agent_error"),
        "resume_kind": resume_kind,
    }
    sc = summary.get("shortcut_log_tail")
    if isinstance(sc, list) and sc:
        evt["shortcut_log_tail"] = sc
    for key in ("llm_input_tokens", "llm_output_tokens", "llm_total_tokens", "llm_model"):
        v = summary.get(key)
        if v is not None:
            evt[key] = v
    subs = summary.get("sub_calls")
    if isinstance(subs, list) and subs:
        evt["sub_calls"] = subs
    cf = summary.get("combat_fingerprint")
    if isinstance(cf, str) and cf:
        evt["combat_fingerprint"] = cf
    cq = summary.get("command_queue")
    if isinstance(cq, list) and cq:
        evt["command_queue"] = cq[:32]
    if idempotency_key:
        evt["idempotency_key"] = idempotency_key
    return evt
