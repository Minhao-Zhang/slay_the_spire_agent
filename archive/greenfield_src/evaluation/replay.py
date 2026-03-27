"""Deterministic replay of ingress sequences for CI (Stage 10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.control_api.agent_runtime import summarize_graph_out
from src.decision_engine.graph import build_agent_graph
from src.trace_telemetry.recorder import record_agent_invocation
from src.trace_telemetry.store import InMemoryTraceStore


@dataclass
class ReplayMetrics:
    """Aggregate stats after a replay run."""

    steps: int = 0
    ingress_steps: int = 0
    resume_steps: int = 0
    emitted_commands: int = 0
    awaiting_interrupt_hits: int = 0
    event_types: dict[str, int] = field(default_factory=dict)
    proposal_terminal_idle: int = 0
    proposal_terminal_executed: int = 0
    proposal_terminal_error: int = 0


def merge_runnable_config(base: RunnableConfig, **overrides: Any) -> RunnableConfig:
    c = dict(base.get("configurable") or {})
    c.update({k: v for k, v in overrides.items() if v is not None})
    return {**base, "configurable": c}


def replay_ingress_only(
    *,
    ingress_bodies: list[dict[str, Any]],
    cfg: RunnableConfig,
    trace_store: InMemoryTraceStore | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Run the compiled agent graph for each ingress body with a fresh checkpointer.

    Returns ``(summaries, raw_outputs)``. Records trace events when ``trace_store``
    is set or ``cfg["configurable"]["trace_store"]`` is an |InMemoryTraceStore|.
    """
    saver = InMemorySaver()
    g = build_agent_graph(checkpointer=saver)
    summaries: list[dict[str, Any]] = []
    raws: list[dict[str, Any]] = []
    use_cfg = cfg
    if trace_store is not None:
        use_cfg = merge_runnable_config(cfg, trace_store=trace_store)
    for body in ingress_bodies:
        out = g.invoke({"ingress_raw": body}, use_cfg)
        raws.append(out)
        summ = summarize_graph_out(out, use_cfg)
        summaries.append(summ)
        record_agent_invocation(
            cfg=use_cfg,
            raw_out=out,
            summary=summ,
            step_kind="ingress",
            store=trace_store,
        )
    return summaries, raws


def replay_with_resume(
    *,
    ingress_body: dict[str, Any],
    resume_payload: Any,
    cfg: RunnableConfig,
    trace_store: InMemoryTraceStore | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One ingress invoke followed by ``Command(resume=...)``."""
    saver = InMemorySaver()
    g = build_agent_graph(checkpointer=saver)
    use_cfg = cfg
    if trace_store is not None:
        use_cfg = merge_runnable_config(cfg, trace_store=trace_store)
    summaries = []
    raws = []
    out1 = g.invoke({"ingress_raw": ingress_body}, use_cfg)
    raws.append(out1)
    s1 = summarize_graph_out(out1, use_cfg)
    summaries.append(s1)
    record_agent_invocation(
        cfg=use_cfg,
        raw_out=out1,
        summary=s1,
        step_kind="ingress",
        store=trace_store,
    )
    rk = None
    if isinstance(resume_payload, dict) and isinstance(resume_payload.get("kind"), str):
        rk = resume_payload["kind"].lower()
    out2 = g.invoke(Command(resume=resume_payload), use_cfg)
    raws.append(out2)
    s2 = summarize_graph_out(out2, use_cfg)
    summaries.append(s2)
    record_agent_invocation(
        cfg=use_cfg,
        raw_out=out2,
        summary=s2,
        step_kind="resume",
        resume_kind=rk,
        store=trace_store,
    )
    return summaries, raws


def compute_replay_metrics(events: list[dict[str, Any]]) -> ReplayMetrics:
    m = ReplayMetrics(steps=len(events))
    for e in events:
        et = str(e.get("event_type") or "")
        m.event_types[et] = m.event_types.get(et, 0) + 1
        sk = e.get("step_kind")
        if sk == "ingress":
            m.ingress_steps += 1
        elif sk == "resume":
            m.resume_steps += 1
        if e.get("emitted_command"):
            m.emitted_commands += 1
        if e.get("awaiting_interrupt"):
            m.awaiting_interrupt_hits += 1
        ps = e.get("proposal_status")
        if ps == "idle":
            m.proposal_terminal_idle += 1
        elif ps == "executed":
            m.proposal_terminal_executed += 1
        elif ps == "error":
            m.proposal_terminal_error += 1
    return m
