"""Server-side command queue for sequential emits (combat only, legacy ``queued_sequence`` parity)."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.decision_engine import shortcuts
from src.decision_engine.proposal_logic import idle_proposal


def drain_command_queue_if_ready(
    state: dict[str, Any],
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Pop one legal command from ``command_queue`` when enabled, manual mode off, and in combat.

    Returns partial state update (may include ``emitted_command``, ``command_queue``, ``proposal``).
    """
    mode = str((config.get("configurable") or {}).get("agent_mode", "propose")).lower()
    if mode == "manual":
        return {}

    q = list(state.get("command_queue") or [])
    if not q:
        return {}

    vm = state.get("view_model")
    if not shortcuts.in_fight(vm):
        tr = list(state.get("decision_trace") or [])
        tr.append("queue:cleared_not_in_combat")
        return {"command_queue": [], "decision_trace": tr}

    from src.agent_core.resolve import resolve_to_legal_command
    from src.agent_core.schemas import StructuredCommandProposal

    head = str(q[0]).strip()
    tail = [str(x).strip() for x in q[1:] if str(x).strip()]
    prop = StructuredCommandProposal(command=head, rationale="")
    resolved, tag = resolve_to_legal_command(vm, prop, allow_fallback=False)
    trace = list(state.get("decision_trace") or [])
    if not resolved:
        trace.append(f"queue:head_unresolved:{tag}")
        trace.append("queue:cleared_stuck")
        return {
            "command_queue": [],
            "decision_trace": trace,
        }

    trace.append(f"queue:emit:{tag}")
    return {
        "command_queue": tail,
        "emitted_command": resolved,
        "proposal": idle_proposal(),
        "decision_trace": trace,
        "failure_streak": 0,
    }
