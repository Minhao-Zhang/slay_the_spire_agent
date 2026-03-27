"""
In-process LangGraph runner for the control API (Stage 6 HITL).

LangGraph ``thread_id`` is derived from the CommunicationMod payload (``run-{seed}``)
or ``run-menu`` when not in-game / seed missing. After ``propose`` hits an interrupt,
call ``POST /api/agent/resume``; resume uses the interrupt's ``thread_id`` even if the
latest ingress maps to ``run-menu``.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from src.control_api.checkpoint_factory import create_checkpointer
from src.decision_engine.graph import build_agent_graph
from src.domain.run_identity import MENU_THREAD_ID, extract_run_seed_and_thread_id
from src.trace_telemetry.recorder import record_agent_invocation
from src.trace_telemetry.runtime import get_app_trace_store, reset_app_trace_store_for_tests

_agent_lock = threading.Lock()
_graph = None
_checkpointer: BaseCheckpointSaver | None = None
_sqlite_conn: sqlite3.Connection | None = None
_last_summary: dict[str, Any] | None = None
_last_run_seed: str | None = None
_last_ingress_derived_thread_id: str | None = None


def reset_agent_runtime_for_tests() -> None:
    global _graph, _checkpointer, _sqlite_conn, _last_summary, _last_run_seed, _last_ingress_derived_thread_id
    with _agent_lock:
        _graph = None
        _checkpointer = None
        _last_summary = None
        _last_run_seed = None
        _last_ingress_derived_thread_id = None
        if _sqlite_conn is not None:
            try:
                _sqlite_conn.close()
            except sqlite3.Error:
                pass
            _sqlite_conn = None
    reset_app_trace_store_for_tests()


def shutdown_checkpoint_resources() -> None:
    """Close SQLite checkpointer connection (FastAPI shutdown)."""
    global _graph, _checkpointer, _sqlite_conn, _last_summary, _last_run_seed, _last_ingress_derived_thread_id
    with _agent_lock:
        _graph = None
        _checkpointer = None
        _last_summary = None
        _last_run_seed = None
        _last_ingress_derived_thread_id = None
        if _sqlite_conn is not None:
            try:
                _sqlite_conn.close()
            except sqlite3.Error:
                pass
            _sqlite_conn = None


def _get_compiled_graph():
    global _graph, _checkpointer, _sqlite_conn
    if _graph is None:
        saver, conn = create_checkpointer()
        _checkpointer = saver
        _sqlite_conn = conn
        _graph = build_agent_graph(checkpointer=saver)
    return _graph


def get_compiled_agent_graph():
    """Read-only access for history/debug endpoints (same instance as invocations)."""
    return _get_compiled_graph()


def agent_mode() -> str:
    m = os.environ.get("SLAY_AGENT_MODE", "propose").strip().lower()
    if m in ("manual", "auto", "propose"):
        return m
    return "propose"


def agent_proposer() -> str:
    p = os.environ.get("SLAY_PROPOSER", "mock").strip().lower()
    return p if p in ("mock", "llm") else "mock"


def agent_llm_backend() -> str:
    b = os.environ.get("SLAY_LLM_BACKEND", "stub").strip().lower()
    return b if b in ("stub", "openai") else "stub"


def agent_memory_max_turns() -> int:
    try:
        n = int(os.environ.get("SLAY_MEMORY_MAX_TURNS", "32"))
        return max(1, min(n, 10_000))
    except ValueError:
        return 32


def _run_config_for_thread(tid: str) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": tid,
            "agent_mode": agent_mode(),
            "proposer": agent_proposer(),
            "memory_max_turns": agent_memory_max_turns(),
        },
    }


def _interrupt_thread_from_summary(summary: dict[str, Any] | None) -> str | None:
    if not summary or not summary.get("awaiting_interrupt"):
        return None
    pend = summary.get("pending_approval")
    if isinstance(pend, dict):
        t = pend.get("thread_id")
        if t is not None:
            return str(t)
    t2 = summary.get("thread_id")
    return str(t2) if t2 is not None else None


def _resolve_ingress_config(
    ingress_body: dict[str, Any],
    *,
    prior_summary: dict[str, Any] | None,
) -> tuple[RunnableConfig, str, str, str]:
    """
    Returns ``(config, run_seed, effective_thread_id, ingress_derived_thread_id)``.
    When HITL is pending, ``effective_thread_id`` is the interrupt thread; ingress
    mapping still returns ``ingress_derived_thread_id`` for status display.
    """
    run_seed, ingress_tid = extract_run_seed_and_thread_id(ingress_body)
    if prior_summary and prior_summary.get("pending_approval") is not None:
        intr = _interrupt_thread_from_summary(prior_summary)
        if intr is not None:
            return _run_config_for_thread(intr), run_seed, intr, ingress_tid

    return _run_config_for_thread(ingress_tid), run_seed, ingress_tid, ingress_tid


def _resolve_resume_config(prior_summary: dict[str, Any] | None) -> RunnableConfig:
    intr = _interrupt_thread_from_summary(prior_summary)
    if intr is None:
        raise ValueError("No pending interrupt thread for resume")
    return _run_config_for_thread(intr)


def _interrupt_payload(entry: Any) -> Any:
    if hasattr(entry, "value"):
        return entry.value
    return entry


def _trace_overlay(summary: dict[str, Any]) -> dict[str, Any]:
    tid = str(summary.get("thread_id") or MENU_THREAD_ID)
    events = get_app_trace_store().list_events(thread_id=tid)
    tail = events[-8:]
    summary["trace_tail"] = [
        {
            "event_type": e.get("event_type"),
            "step_seq": e.get("step_seq"),
            "step_kind": e.get("step_kind"),
            "state_id": e.get("state_id"),
            "proposal_status": e.get("proposal_status"),
        }
        for e in tail
    ]
    summary["trace_event_count"] = len(events)
    return summary


def _llm_fields_from_proposal(proposal: Any) -> dict[str, Any]:
    """Copy usage/model from nested ``proposal.parsed_model`` to summary top-level."""
    if not isinstance(proposal, dict):
        return {}
    pm = proposal.get("parsed_model")
    if not isinstance(pm, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("llm_input_tokens", "llm_output_tokens", "llm_total_tokens", "llm_model"):
        v = pm.get(key)
        if v is not None:
            out[key] = v
    sc = pm.get("sub_calls")
    if isinstance(sc, list) and sc:
        out["sub_calls"] = sc
    return out


def summarize_graph_out(out: dict[str, Any], cfg: RunnableConfig) -> dict[str, Any]:
    pending = None
    if "__interrupt__" in out:
        first = out["__interrupt__"][0]
        payload = _interrupt_payload(first)
        pending = {
            "interrupt": payload,
            "thread_id": (cfg.get("configurable") or {}).get("thread_id"),
        }
    emitted = out.get("emitted_command")
    trace = out.get("decision_trace") or []
    if isinstance(trace, list):
        tail = trace[-12:]
    else:
        tail = []
    mem = out.get("memory_log")
    mem_list = mem if isinstance(mem, list) else []
    mem_tail = mem_list[-8:] if mem_list else []
    sid = out.get("state_id")
    conf = cfg.get("configurable") or {}
    tid = conf.get("thread_id")
    mode = conf.get("agent_mode")
    sc_log = out.get("shortcut_log")
    sc_tail = (
        list(sc_log)[-20:]
        if isinstance(sc_log, list) and sc_log
        else []
    )
    summ: dict[str, Any] = {
        "state_id": str(sid) if sid is not None else None,
        "pending_approval": pending,
        "emitted_command": emitted,
        "proposal": out.get("proposal"),
        "failure_streak": out.get("failure_streak", 0),
        "decision_trace": tail,
        "shortcut_log_tail": sc_tail,
        "awaiting_interrupt": pending is not None,
        "agent_mode": str(mode).lower() if mode is not None else agent_mode(),
        "thread_id": str(tid) if tid is not None else MENU_THREAD_ID,
        "memory_turns": len(mem_list),
        "memory_tail": mem_tail,
        "combat_fingerprint": out.get("combat_fingerprint"),
        "command_queue": out.get("command_queue"),
    }
    summ.update(_llm_fields_from_proposal(out.get("proposal")))
    return summ


def _ingest_ingress_labels(
    ingress_body: dict[str, Any],
    effective_tid: str,
    ingress_derived_tid: str,
) -> None:
    global _last_run_seed, _last_ingress_derived_thread_id
    _last_run_seed, _ = extract_run_seed_and_thread_id(ingress_body)
    _last_ingress_derived_thread_id = ingress_derived_tid
    _ = effective_tid


def retry_agent(ingress_body: dict[str, Any], queue_manual) -> dict[str, Any]:
    """
    Re-run the graph for the same ingress (fresh LLM / mock proposal).

    If HITL left the last run waiting on ``interrupt``, resumes with **reject**
    first so the checkpointer can accept a new ``ingress_raw`` invoke (same
    LangGraph thread as the interrupt until cleared).
    """
    global _last_summary
    try:
        g = _get_compiled_graph()
        with _agent_lock:
            if _last_summary and _last_summary.get("pending_approval") is not None:
                cfg_rej = _resolve_resume_config(_last_summary)
                out_rej = g.invoke(Command(resume="reject"), cfg_rej)
                summ_rej = summarize_graph_out(out_rej, cfg_rej)
                _last_summary = summ_rej
                record_agent_invocation(
                    cfg=cfg_rej,
                    raw_out=out_rej,
                    summary=summ_rej,
                    step_kind="resume",
                    resume_kind="reject",
                )
                _trace_overlay(summ_rej)
            cfg, _, eff_tid, ingress_tid = _resolve_ingress_config(ingress_body, prior_summary=_last_summary)
            _ingest_ingress_labels(ingress_body, eff_tid, ingress_tid)
            out = g.invoke({"ingress_raw": ingress_body}, cfg)
            summary = summarize_graph_out(out, cfg)
            _last_summary = summary
            record_agent_invocation(
                cfg=cfg,
                raw_out=out,
                summary=summary,
                step_kind="ingress",
            )
            _trace_overlay(summary)
            emitted = summary.get("emitted_command")
            if emitted and not summary.get("pending_approval"):
                queue_manual(str(emitted))
        return summary
    except Exception as e:
        with _agent_lock:
            prior = _last_summary
        cfg_fallback, _, _, _ = _resolve_ingress_config(ingress_body, prior_summary=prior)
        summary = summarize_graph_out({"decision_trace": [f"agent_error:{e}"]}, cfg_fallback)
        summary["agent_error"] = str(e)
        with _agent_lock:
            _last_summary = summary
        record_agent_invocation(
            cfg=cfg_fallback,
            raw_out={},
            summary=summary,
            step_kind="ingress",
        )
        _trace_overlay(summary)
        return summary


def step_ingress(ingress_body: dict[str, Any], queue_manual) -> dict[str, Any]:
    """Run the graph for a new CommunicationMod payload (after projection)."""
    global _last_summary
    try:
        g = _get_compiled_graph()
        with _agent_lock:
            cfg, _, eff_tid, ingress_tid = _resolve_ingress_config(ingress_body, prior_summary=_last_summary)
            _ingest_ingress_labels(ingress_body, eff_tid, ingress_tid)
            out = g.invoke({"ingress_raw": ingress_body}, cfg)
            summary = summarize_graph_out(out, cfg)
            _last_summary = summary
            record_agent_invocation(
                cfg=cfg,
                raw_out=out,
                summary=summary,
                step_kind="ingress",
            )
            _trace_overlay(summary)
            emitted = summary.get("emitted_command")
            if emitted and not summary.get("pending_approval"):
                queue_manual(str(emitted))
        return summary
    except Exception as e:
        with _agent_lock:
            prior = _last_summary
        cfg_fallback, _, _, _ = _resolve_ingress_config(ingress_body, prior_summary=prior)
        summary = summarize_graph_out({"decision_trace": [f"agent_error:{e}"]}, cfg_fallback)
        summary["agent_error"] = str(e)
        with _agent_lock:
            _last_summary = summary
        record_agent_invocation(
            cfg=cfg_fallback,
            raw_out={},
            summary=summary,
            step_kind="ingress",
        )
        _trace_overlay(summary)
        return summary


def resume_agent(body: dict[str, Any], queue_manual) -> dict[str, Any]:
    global _last_summary
    kind = body.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise ValueError("kind required (approve | reject | edit)")
    k = kind.strip().lower()
    resume: Any
    if k == "approve":
        resume = {"kind": "approve"}
    elif k == "reject":
        resume = "reject"
    elif k == "edit":
        cmd = body.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise ValueError("command required for edit")
        resume = {"kind": "edit", "command": " ".join(cmd.strip().split())}
    else:
        raise ValueError("kind must be approve, reject, or edit")

    g = _get_compiled_graph()
    try:
        with _agent_lock:
            cfg = _resolve_resume_config(_last_summary)
            out = g.invoke(Command(resume=resume), cfg)
            summary = summarize_graph_out(out, cfg)
            _last_summary = summary
            record_agent_invocation(
                cfg=cfg,
                raw_out=out,
                summary=summary,
                step_kind="resume",
                resume_kind=k,
            )
            _trace_overlay(summary)
            emitted = summary.get("emitted_command")
            if emitted and not summary.get("pending_approval"):
                queue_manual(str(emitted))
        return summary
    except Exception as e:
        with _agent_lock:
            ps = _last_summary
        try:
            cfg_fb = _resolve_resume_config(ps)
        except ValueError:
            tid = (ps or {}).get("thread_id")
            cfg_fb = _run_config_for_thread(str(tid) if tid else MENU_THREAD_ID)
        summary = summarize_graph_out({"decision_trace": [f"resume_error:{e}"]}, cfg_fb)
        summary["agent_error"] = str(e)
        with _agent_lock:
            _last_summary = summary
        record_agent_invocation(
            cfg=cfg_fb,
            raw_out={},
            summary=summary,
            step_kind="resume",
            resume_kind=k,
        )
        _trace_overlay(summary)
        return summary


def get_agent_status() -> dict[str, Any]:
    with _agent_lock:
        if _last_summary is None:
            d = {
                "state_id": None,
                "pending_approval": None,
                "emitted_command": None,
                "proposal": None,
                "failure_streak": 0,
                "decision_trace": [],
                "awaiting_interrupt": False,
                "proposer": agent_proposer(),
                "llm_backend": agent_llm_backend(),
                "memory_turns": 0,
                "memory_tail": [],
                "trace_tail": [],
                "trace_event_count": 0,
                "thread_id": None,
                "run_seed": _last_run_seed,
            }
        else:
            d = dict(_last_summary)
    d["agent_mode"] = agent_mode()
    d["proposer"] = agent_proposer()
    d["llm_backend"] = agent_llm_backend()
    d["memory_max_turns"] = agent_memory_max_turns()
    d["run_seed"] = _last_run_seed
    eff = d.get("thread_id")
    if d.get("pending_approval") and _last_ingress_derived_thread_id and eff != _last_ingress_derived_thread_id:
        d["ingress_derived_thread_id"] = _last_ingress_derived_thread_id
        pend_tid = None
        pa = d.get("pending_approval")
        if isinstance(pa, dict):
            pend_tid = pa.get("thread_id")
        if pend_tid is not None:
            d["pending_graph_thread_id"] = str(pend_tid)

    if "memory_turns" not in d:
        d["memory_turns"] = 0
    if "memory_tail" not in d:
        d["memory_tail"] = []
    _trace_overlay(d)
    return d
