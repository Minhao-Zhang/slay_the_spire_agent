"""
LangGraph decision engine: ingest → project → mode-specific proposal policy.

- ``manual``: no mock proposal; ends idle.
- ``auto``: mock first legal command → executed (no interrupt).
- ``propose``: mock command → ``interrupt`` → resume with approve / reject / edit.

Configure per invoke::

    {"configurable": {"thread_id": "...", "agent_mode": "propose|auto|manual"}}

Optional: ``now`` (float, tests), ``proposal_ttl_seconds`` (default 300).
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from src.domain.contracts import compute_state_id, parse_ingress_envelope
from src.domain.state_projection import project_state
from src.decision_engine.proposal_logic import (
    apply_hygiene_on_proposal,
    coalesce_proposal,
    finalize_approval,
    graph_now,
    idle_proposal,
)
from src.decision_engine.proposer import propose_for_view_model
from src.memory.graph_nodes import memory_update_node


class AgentGraphState(TypedDict, total=False):
    """Checkpoint-friendly graph state (plain JSON types)."""

    ingress_raw: dict[str, Any]
    state_id: str | None
    view_model: dict[str, Any] | None
    proposal: dict[str, Any] | None
    emitted_command: str | None
    decision_trace: list[str]
    failure_streak: int
    memory_log: list[dict[str, Any]]
    memory_seq_cursor: int


def _ingest_and_project(state: AgentGraphState) -> dict[str, Any]:
    raw = state.get("ingress_raw")
    if not raw:
        raise ValueError("ingress_raw is required on first input")
    ingress = parse_ingress_envelope(raw)
    sid = compute_state_id(ingress)
    vm = project_state(ingress)
    return {
        "state_id": sid,
        "view_model": vm.model_dump(mode="json", by_alias=True),
    }


def _proposal_hygiene(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    now = graph_now(config)
    sid = state.get("state_id")
    old = coalesce_proposal(state.get("proposal"))
    old_status = old.get("status")
    p, hy_trace = apply_hygiene_on_proposal(
        state_id=sid,
        proposal=state.get("proposal"),
        now=now,
    )
    trace = list(state.get("decision_trace") or [])
    trace.extend(hy_trace)
    streak = state.get("failure_streak") or 0
    if p.get("status") == "error" and old_status != "error":
        streak += 1
    elif p.get("status") in ("executed", "idle", "stale"):
        streak = 0

    if (
        sid
        and p.get("for_state_id")
        and p["for_state_id"] != sid
        and p.get("status") in ("executed", "error", "stale")
    ):
        p = idle_proposal()
        trace.append("reset:new_state_after_terminal")
        streak = 0

    return {"proposal": p, "decision_trace": trace, "failure_streak": streak}


def _route_mode(_state: AgentGraphState, config: RunnableConfig) -> str:
    mode = (config.get("configurable") or {}).get("agent_mode", "propose")
    if mode == "manual":
        return "manual"
    if mode == "auto":
        return "auto"
    return "propose"


def _manual_lane(state: AgentGraphState) -> dict[str, Any]:
    trace = list(state.get("decision_trace") or [])
    trace.append("mode:manual")
    return {
        "proposal": idle_proposal(),
        "emitted_command": None,
        "decision_trace": trace,
        "failure_streak": 0,
    }


def _proposal_ttl(config: RunnableConfig) -> float:
    raw = (config.get("configurable") or {}).get("proposal_ttl_seconds", 300.0)
    return float(raw)


def _rationale_and_resolve_tag(
    *,
    resolve_tag: str,
    parsed: dict[str, Any] | None,
) -> tuple[str | None, str]:
    """
    ``rationale`` = model text from parsed JSON (LLM or mock echo);
    ``resolve_tag`` = post-parse resolver label (e.g. ``resolved:direct``).
    """
    human: str | None = None
    if parsed:
        raw_r = parsed.get("rationale")
        if isinstance(raw_r, str) and raw_r.strip():
            human = raw_r.strip()
    return human, resolve_tag


def _auto_lane(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    trace = list(state.get("decision_trace") or [])
    trace.append("mode:auto")
    vm = state.get("view_model")
    sid = state.get("state_id")
    cmd, why, raw, parsed = propose_for_view_model(vm, config)
    now = graph_now(config)
    rat, tag = _rationale_and_resolve_tag(resolve_tag=why, parsed=parsed)
    if not cmd:
        trace.append(f"error:{why}")
        p = coalesce_proposal(
            {
                **idle_proposal(),
                "status": "error",
                "for_state_id": sid,
                "error_reason": why,
                "rationale": rat,
                "resolve_tag": tag,
                "llm_raw": raw,
                "parsed_model": parsed,
            },
        )
        return {
            "proposal": p,
            "emitted_command": None,
            "decision_trace": trace,
            "failure_streak": (state.get("failure_streak") or 0) + 1,
        }
    trace.append("executed:auto")
    p = coalesce_proposal(
        {
            **idle_proposal(),
            "status": "executed",
            "for_state_id": sid,
            "command": cmd,
            "rationale": rat,
            "resolve_tag": tag,
            "expires_at": None,
            "llm_raw": raw,
            "parsed_model": parsed,
        },
    )
    return {
        "proposal": p,
        "emitted_command": cmd,
        "decision_trace": trace,
        "failure_streak": 0,
    }


def _propose_lane(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    trace = list(state.get("decision_trace") or [])
    trace.append("mode:propose:prepare")
    vm = state.get("view_model")
    sid = state.get("state_id")
    cmd, why, raw, parsed = propose_for_view_model(vm, config)
    now = graph_now(config)
    ttl = _proposal_ttl(config)
    rat, tag = _rationale_and_resolve_tag(resolve_tag=why, parsed=parsed)
    if not cmd:
        trace.append(f"error:{why}")
        p = coalesce_proposal(
            {
                **idle_proposal(),
                "status": "error",
                "for_state_id": sid,
                "error_reason": why,
                "rationale": rat,
                "resolve_tag": tag,
                "llm_raw": raw,
                "parsed_model": parsed,
            },
        )
        return {
            "proposal": p,
            "emitted_command": None,
            "decision_trace": trace,
            "failure_streak": (state.get("failure_streak") or 0) + 1,
        }
    p = coalesce_proposal(
        {
            **idle_proposal(),
            "status": "awaiting_approval",
            "for_state_id": sid,
            "command": cmd,
            "rationale": rat,
            "resolve_tag": tag,
            "expires_at": now + ttl,
            "llm_raw": raw,
            "parsed_model": parsed,
        },
    )
    return {"proposal": p, "decision_trace": trace}


def _route_after_propose_setup(state: AgentGraphState) -> str:
    p = coalesce_proposal(state.get("proposal"))
    if p.get("status") == "awaiting_approval":
        return "hitl"
    return "done"


def _approval_interrupt(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    trace = list(state.get("decision_trace") or [])
    p = coalesce_proposal(state.get("proposal"))
    now = graph_now(config)
    if p.get("expires_at") is not None and now > float(p["expires_at"]):
        trace.append("error:approval_timeout_at_interrupt")
        p2 = coalesce_proposal(
            {**p, "status": "error", "error_reason": "approval_timeout"},
        )
        return {
            "proposal": p2,
            "emitted_command": None,
            "decision_trace": trace,
            "failure_streak": (state.get("failure_streak") or 0) + 1,
        }
    payload = {"state_id": p.get("for_state_id"), "command": p.get("command")}
    resume = interrupt(payload)
    new_p, emitted, fin_trace = finalize_approval(
        current_state_id=state.get("state_id"),
        view_model=state.get("view_model"),
        proposal=p,
        resume=resume,
    )
    trace.extend(fin_trace)
    streak = state.get("failure_streak") or 0
    if new_p.get("status") == "error":
        streak += 1
    elif new_p.get("status") == "executed":
        streak = 0
    elif new_p.get("status") == "stale":
        streak = 0
    return {
        "proposal": new_p,
        "emitted_command": emitted,
        "decision_trace": trace,
        "failure_streak": streak,
    }


def build_agent_graph(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """
    Compile the Stage 5 graph (modes + proposal lifecycle).

    Default ``agent_mode`` when omitted: ``propose`` (interrupt before execute).
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()

    g = StateGraph(AgentGraphState)
    g.add_node("ingest_project", _ingest_and_project)
    g.add_node("memory_update", memory_update_node)
    g.add_node("proposal_hygiene", _proposal_hygiene)
    g.add_node("manual_lane", _manual_lane)
    g.add_node("auto_lane", _auto_lane)
    g.add_node("propose_lane", _propose_lane)
    g.add_node("approval_interrupt", _approval_interrupt)

    g.add_edge(START, "ingest_project")
    g.add_edge("ingest_project", "memory_update")
    g.add_edge("memory_update", "proposal_hygiene")
    g.add_conditional_edges(
        "proposal_hygiene",
        _route_mode,
        {
            "manual": "manual_lane",
            "auto": "auto_lane",
            "propose": "propose_lane",
        },
    )
    g.add_edge("manual_lane", END)
    g.add_edge("auto_lane", END)
    g.add_conditional_edges(
        "propose_lane",
        _route_after_propose_setup,
        {"hitl": "approval_interrupt", "done": END},
    )
    g.add_edge("approval_interrupt", END)

    return g.compile(checkpointer=checkpointer)
