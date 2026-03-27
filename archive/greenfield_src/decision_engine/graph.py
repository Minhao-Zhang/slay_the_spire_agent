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

from src.domain.combat_fingerprint import combat_encounter_fingerprint
from src.domain.contracts import compute_state_id, parse_ingress_envelope
from src.domain.legal_command import is_command_legal
from src.domain.state_projection import project_state
from src.decision_engine.proposal_logic import (
    apply_hygiene_on_proposal,
    coalesce_proposal,
    finalize_approval,
    graph_now,
    idle_proposal,
)
from src.decision_engine import shortcuts
from src.decision_engine.command_queue import drain_command_queue_if_ready
from src.decision_engine.proposer import propose_for_view_model
from src.memory.graph_nodes import memory_update_node

_SHORTCUT_LOG_CAP = 500


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
    shortcut_log: list[dict[str, Any]]
    combat_fingerprint: str | None
    command_queue: list[str]


def _ingest_and_project(state: AgentGraphState) -> dict[str, Any]:
    raw = state.get("ingress_raw")
    if not raw:
        raise ValueError("ingress_raw is required on first input")
    ingress = parse_ingress_envelope(raw)
    sid = compute_state_id(ingress)
    vm = project_state(ingress)
    vm_dict = vm.model_dump(mode="json", by_alias=True)
    prev_sid = state.get("state_id")
    out: dict[str, Any] = {
        "state_id": sid,
        "view_model": vm_dict,
        "combat_fingerprint": combat_encounter_fingerprint(vm_dict),
    }
    if prev_sid is not None and prev_sid != sid:
        out["command_queue"] = []
    return out


def _tail_from_parsed(
    vm: dict[str, Any] | None,
    parsed: dict[str, Any] | None,
) -> list[str]:
    if not parsed or not shortcuts.in_fight(vm):
        return []
    raw = parsed.get("command_queue_tail")
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _command_queue_try(
    state: AgentGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    return drain_command_queue_if_ready(state, config)


def _route_after_queue_try(state: AgentGraphState) -> str:
    if state.get("emitted_command"):
        return "done"
    return "continue"


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

    vm = state.get("view_model")
    cmd0 = p.get("command")
    if (
        vm
        and sid
        and p.get("for_state_id") == sid
        and p.get("status") == "executed"
        and cmd0
        and str(cmd0).strip()
        and not is_command_legal(vm, str(cmd0).strip())
    ):
        p = idle_proposal()
        trace.append("reset:executed_not_legal_on_vm")
        streak = 0

    return {"proposal": p, "decision_trace": trace, "failure_streak": streak}


def _append_shortcut_entry(
    state: AgentGraphState,
    config: RunnableConfig,
    *,
    kind: str,
    command: str,
) -> dict[str, Any]:
    slog = list(state.get("shortcut_log") or [])
    entry: dict[str, Any] = {
        "kind": kind,
        "command": command,
        "state_id": state.get("state_id"),
        "ts_logical": graph_now(config),
    }
    slog.append(entry)
    if len(slog) > _SHORTCUT_LOG_CAP:
        slog = slog[-_SHORTCUT_LOG_CAP:]
    trace = list(state.get("decision_trace") or [])
    trace.append(f"shortcut:{kind}:{command}")
    return {"shortcut_log": slog, "decision_trace": trace}


def _route_after_hygiene(state: AgentGraphState, config: RunnableConfig) -> str:
    mode = (config.get("configurable") or {}).get("agent_mode", "propose")
    if mode == "manual":
        return "manual"
    raw = state.get("ingress_raw") or {}
    vm = state.get("view_model") or {}
    if (
        shortcuts.shortcuts_enabled()
        and not shortcuts.in_fight(vm)
        and raw.get("ready_for_command")
        and (vm.get("actions") or [])
    ):
        cmd, kind = shortcuts.try_deterministic_shortcut(raw, vm)
        if cmd and kind:
            return "shortcut_auto" if mode == "auto" else "shortcut_propose"
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


def _shortcut_auto_lane(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    raw = state.get("ingress_raw") or {}
    vm = state.get("view_model") or {}
    sid = state.get("state_id")
    cmd, kind = shortcuts.try_deterministic_shortcut(raw, vm)
    if not cmd or not kind:
        return _auto_lane(state, config)
    upd = _append_shortcut_entry(state, config, kind=kind, command=cmd)
    trace = list(upd["decision_trace"])
    trace.append("mode:shortcut:auto")
    rat = f"Deterministic shortcut ({kind})"
    tag = f"shortcut:{kind}"
    p = coalesce_proposal(
        {
            **idle_proposal(),
            "status": "executed",
            "for_state_id": sid,
            "command": cmd,
            "rationale": rat,
            "resolve_tag": tag,
            "expires_at": None,
            "llm_raw": None,
            "parsed_model": {"command": cmd, "rationale": rat, "shortcut_kind": kind},
        },
    )
    return {
        **upd,
        "proposal": p,
        "emitted_command": cmd,
        "decision_trace": trace,
        "failure_streak": 0,
    }


def _shortcut_propose_lane(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    raw = state.get("ingress_raw") or {}
    vm = state.get("view_model") or {}
    sid = state.get("state_id")
    cmd, kind = shortcuts.try_deterministic_shortcut(raw, vm)
    if not cmd or not kind:
        return _propose_lane(state, config)
    upd = _append_shortcut_entry(state, config, kind=kind, command=cmd)
    trace = list(upd["decision_trace"])
    trace.append("mode:shortcut:propose")
    now = graph_now(config)
    ttl = _proposal_ttl(config)
    rat = f"Deterministic shortcut ({kind}) — approve to execute"
    tag = f"shortcut:{kind}"
    p = coalesce_proposal(
        {
            **idle_proposal(),
            "status": "awaiting_approval",
            "for_state_id": sid,
            "command": cmd,
            "rationale": rat,
            "resolve_tag": tag,
            "expires_at": now + ttl,
            "llm_raw": None,
            "parsed_model": {"command": cmd, "rationale": rat, "shortcut_kind": kind},
        },
    )
    return {**upd, "proposal": p, "decision_trace": trace}


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
            "command_queue": [],
        }
    trace.append("executed:auto")
    tail = _tail_from_parsed(vm, parsed)
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
    out: dict[str, Any] = {
        "proposal": p,
        "emitted_command": cmd,
        "decision_trace": trace,
        "failure_streak": 0,
    }
    if tail:
        out["command_queue"] = tail
    return out


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
            "command_queue": [],
        }
    tail = _tail_from_parsed(vm, parsed)
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
            "command_queue": tail,
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
        p2.pop("command_queue", None)
        return {
            "proposal": p2,
            "emitted_command": None,
            "decision_trace": trace,
            "failure_streak": (state.get("failure_streak") or 0) + 1,
            "command_queue": [],
        }
    tail = [str(x).strip() for x in (p.get("command_queue") or []) if str(x).strip()]
    payload = {
        "state_id": p.get("for_state_id"),
        "command": p.get("command"),
        "command_queue": tail,
    }
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
    out: dict[str, Any] = {
        "proposal": new_p,
        "emitted_command": emitted,
        "decision_trace": trace,
        "failure_streak": streak,
    }
    if new_p.get("status") == "executed" and emitted is not None:
        out["command_queue"] = list(tail)
    elif new_p.get("status") == "error":
        out["command_queue"] = []
    elif new_p.get("status") == "stale" and new_p.get("error_reason") == "state_advanced":
        out["command_queue"] = []
    return out


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
    g.add_node("command_queue_try", _command_queue_try)
    g.add_node("proposal_hygiene", _proposal_hygiene)
    g.add_node("manual_lane", _manual_lane)
    g.add_node("shortcut_auto", _shortcut_auto_lane)
    g.add_node("shortcut_propose", _shortcut_propose_lane)
    g.add_node("auto_lane", _auto_lane)
    g.add_node("propose_lane", _propose_lane)
    g.add_node("approval_interrupt", _approval_interrupt)

    g.add_edge(START, "ingest_project")
    g.add_edge("ingest_project", "memory_update")
    g.add_edge("memory_update", "command_queue_try")
    g.add_conditional_edges(
        "command_queue_try",
        _route_after_queue_try,
        {
            "done": END,
            "continue": "proposal_hygiene",
        },
    )
    g.add_conditional_edges(
        "proposal_hygiene",
        _route_after_hygiene,
        {
            "manual": "manual_lane",
            "shortcut_auto": "shortcut_auto",
            "shortcut_propose": "shortcut_propose",
            "auto": "auto_lane",
            "propose": "propose_lane",
        },
    )
    g.add_edge("manual_lane", END)
    g.add_edge("shortcut_auto", END)
    g.add_edge("auto_lane", END)
    g.add_conditional_edges(
        "shortcut_propose",
        _route_after_propose_setup,
        {"hitl": "approval_interrupt", "done": END},
    )
    g.add_conditional_edges(
        "propose_lane",
        _route_after_propose_setup,
        {"hitl": "approval_interrupt", "done": END},
    )
    g.add_edge("approval_interrupt", END)

    return g.compile(checkpointer=checkpointer)
