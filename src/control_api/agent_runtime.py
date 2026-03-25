"""
In-process LangGraph runner for the control API (Stage 6 HITL).

``SLAY_AGENT_THREAD_ID`` (default ``default``) and ``SLAY_AGENT_MODE`` (default
``propose``) select graph config. After ``propose`` hits an interrupt, call
``POST /api/agent/resume``; completed ``emitted_command`` values are queued for
``poll_instruction`` / ``main.py`` like other manual actions.
"""

from __future__ import annotations

import os
import threading
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.decision_engine.graph import build_agent_graph
from src.trace_telemetry.recorder import record_agent_invocation
from src.trace_telemetry.runtime import get_app_trace_store, reset_app_trace_store_for_tests

_agent_lock = threading.Lock()
_graph = None
_checkpointer: InMemorySaver | None = None
_last_summary: dict[str, Any] | None = None


def reset_agent_runtime_for_tests() -> None:
    global _graph, _checkpointer, _last_summary
    with _agent_lock:
        _graph = None
        _checkpointer = None
        _last_summary = None
    reset_app_trace_store_for_tests()


def _get_compiled_graph():
    global _graph, _checkpointer
    if _graph is None:
        _checkpointer = InMemorySaver()
        _graph = build_agent_graph(checkpointer=_checkpointer)
    return _graph


def agent_thread_id() -> str:
    return os.environ.get("SLAY_AGENT_THREAD_ID", "default")


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


def _run_config() -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": agent_thread_id(),
            "agent_mode": agent_mode(),
            "proposer": agent_proposer(),
            "memory_max_turns": agent_memory_max_turns(),
        },
    }


def _interrupt_payload(entry: Any) -> Any:
    if hasattr(entry, "value"):
        return entry.value
    return entry


def _trace_overlay(summary: dict[str, Any]) -> dict[str, Any]:
    tid = str(summary.get("thread_id") or agent_thread_id())
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
    return {
        "state_id": str(sid) if sid is not None else None,
        "pending_approval": pending,
        "emitted_command": emitted,
        "proposal": out.get("proposal"),
        "failure_streak": out.get("failure_streak", 0),
        "decision_trace": tail,
        "awaiting_interrupt": pending is not None,
        "agent_mode": str(mode).lower() if mode is not None else agent_mode(),
        "thread_id": str(tid) if tid is not None else agent_thread_id(),
        "memory_turns": len(mem_list),
        "memory_tail": mem_tail,
    }


def retry_agent(ingress_body: dict[str, Any], queue_manual) -> dict[str, Any]:
    """
    Re-run the graph for the same ingress (fresh LLM / mock proposal).

    If HITL left the last run waiting on ``interrupt``, resumes with **reject**
    first so the checkpointer can accept a new ``ingress_raw`` invoke (same
    LangGraph ``thread_id``).
    """
    global _last_summary
    cfg = _run_config()
    try:
        g = _get_compiled_graph()
        with _agent_lock:
            if _last_summary and _last_summary.get("pending_approval") is not None:
                out_rej = g.invoke(Command(resume="reject"), cfg)
                summ_rej = summarize_graph_out(out_rej, cfg)
                _last_summary = summ_rej
                record_agent_invocation(
                    cfg=cfg,
                    raw_out=out_rej,
                    summary=summ_rej,
                    step_kind="resume",
                    resume_kind="reject",
                )
                _trace_overlay(summ_rej)
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
        summary = summarize_graph_out({"decision_trace": [f"agent_error:{e}"]}, cfg)
        summary["agent_error"] = str(e)
        with _agent_lock:
            _last_summary = summary
        record_agent_invocation(
            cfg=cfg,
            raw_out={},
            summary=summary,
            step_kind="ingress",
        )
        _trace_overlay(summary)
        return summary


def step_ingress(ingress_body: dict[str, Any], queue_manual) -> dict[str, Any]:
    """Run the graph for a new CommunicationMod payload (after projection)."""
    global _last_summary
    cfg = _run_config()
    try:
        g = _get_compiled_graph()
        with _agent_lock:
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
        summary = summarize_graph_out({"decision_trace": [f"agent_error:{e}"]}, cfg)
        summary["agent_error"] = str(e)
        with _agent_lock:
            _last_summary = summary
        record_agent_invocation(
            cfg=cfg,
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

    cfg = _run_config()
    g = _get_compiled_graph()
    try:
        with _agent_lock:
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
        summary = summarize_graph_out({"decision_trace": [f"resume_error:{e}"]}, cfg)
        summary["agent_error"] = str(e)
        with _agent_lock:
            _last_summary = summary
        record_agent_invocation(
            cfg=cfg,
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
            }
        else:
            d = dict(_last_summary)
    # Config is per-process env; reflect current values even if summary is stale.
    d["agent_mode"] = agent_mode()
    d["thread_id"] = agent_thread_id()
    d["proposer"] = agent_proposer()
    d["llm_backend"] = agent_llm_backend()
    d["memory_max_turns"] = agent_memory_max_turns()
    if "memory_turns" not in d:
        d["memory_turns"] = 0
    if "memory_tail" not in d:
        d["memory_tail"] = []
    _trace_overlay(d)
    return d
