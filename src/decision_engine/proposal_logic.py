"""Pure helpers for proposal status, mock proposals, and approval finalization (no LangGraph)."""

from __future__ import annotations

import time
from typing import Any

from src.domain.legal_command import is_command_legal


def idle_proposal() -> dict[str, Any]:
    return {
        "status": "idle",
        "for_state_id": None,
        "command": None,
        "error_reason": None,
        "expires_at": None,
        "rationale": None,
        "resolve_tag": None,
    }


def coalesce_proposal(p: dict[str, Any] | None) -> dict[str, Any]:
    return {**idle_proposal(), **(p or {})}


def mock_propose_command(view_model: dict[str, Any] | None) -> tuple[str | None, str]:
    """Picks the first legal action (Stage 5 stand-in for LLM)."""
    if not view_model:
        return None, "no_view_model"
    actions = view_model.get("actions") or []
    if not actions:
        return None, "no_actions"
    cmd = actions[0].get("command")
    if not cmd:
        return None, "empty_command"
    return str(cmd).strip(), "mock_first_action"


def apply_hygiene_on_proposal(
    *,
    state_id: str | None,
    proposal: dict[str, Any] | None,
    now: float,
) -> tuple[dict[str, Any], list[str]]:
    """
    Drop stale / timed-out awaiting proposals. Returns (updated_proposal, trace_lines).
    """
    trace: list[str] = []
    p = coalesce_proposal(proposal)

    if (
        state_id
        and p.get("status") == "awaiting_approval"
        and p.get("for_state_id")
        and p["for_state_id"] != state_id
    ):
        p = coalesce_proposal(
            {**p, "status": "stale", "error_reason": "state_id_changed"},
        )
        trace.append("stale:state_id_changed")

    if (
        p.get("status") == "awaiting_approval"
        and p.get("expires_at") is not None
        and now > float(p["expires_at"])
    ):
        p = coalesce_proposal(
            {**p, "status": "error", "error_reason": "approval_timeout"},
        )
        trace.append("error:approval_timeout")

    return p, trace


def finalize_approval(
    *,
    current_state_id: str | None,
    view_model: dict[str, Any] | None,
    proposal: dict[str, Any],
    resume: Any,
) -> tuple[dict[str, Any], str | None, list[str]]:
    """
    Apply human decision after interrupt. Returns (new_proposal, emitted_command_or_none, trace).
    """
    trace: list[str] = []
    p = coalesce_proposal(proposal)
    for_sid = p.get("for_state_id")
    if current_state_id != for_sid:
        trace.append("stale:advance_before_approval")
        return (
            coalesce_proposal({**p, "status": "stale", "error_reason": "state_advanced"}),
            None,
            trace,
        )

    if resume is None or resume == "reject":
        trace.append("rejected")
        return (
            coalesce_proposal({**p, "status": "stale", "error_reason": "rejected"}),
            None,
            trace,
        )

    kind: str | None = None
    cmd_out: str | None = None
    if isinstance(resume, dict):
        kind = str(resume.get("kind", "")).lower()
        cmd_out = resume.get("command")
        if cmd_out is not None:
            cmd_out = str(cmd_out).strip()
    elif resume == "approve":
        kind = "approve"
    else:
        trace.append("error:bad_resume_shape")
        return (
            coalesce_proposal({**p, "status": "error", "error_reason": "bad_resume"}),
            None,
            trace,
        )

    if kind == "approve":
        cmd = p.get("command")
        if not cmd or not is_command_legal(view_model, str(cmd)):
            trace.append("error:illegal_proposed_command")
            return (
                coalesce_proposal({**p, "status": "error", "error_reason": "illegal_proposed"}),
                None,
                trace,
            )
        trace.append("executed:approved")
        return (
            coalesce_proposal({**p, "status": "executed", "error_reason": None}),
            str(cmd).strip(),
            trace,
        )

    if kind == "edit" and cmd_out:
        if not is_command_legal(view_model, cmd_out):
            trace.append("error:illegal_edit")
            return (
                coalesce_proposal({**p, "status": "error", "error_reason": "illegal_edit"}),
                None,
                trace,
            )
        trace.append("executed:edited")
        return (
            coalesce_proposal({**p, "status": "executed", "error_reason": None}),
            cmd_out,
            trace,
        )

    trace.append("error:unsupported_resume")
    return (
        coalesce_proposal({**p, "status": "error", "error_reason": "unsupported_resume"}),
        None,
        trace,
    )


def graph_now(config: dict | None) -> float:
    conf = (config or {}).get("configurable") or {}
    if conf.get("now") is not None:
        return float(conf["now"])
    return time.time()
