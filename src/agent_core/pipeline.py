"""Build prompts, call gateway, parse + resolve (tactical slice)."""

from __future__ import annotations

import json
from typing import Any

from src.agent_core.parse import parse_proposal_json
from src.agent_core.resolve import resolve_to_legal_command
from src.agent_core.state_prompt import build_tactical_state_summary
from src.llm_gateway.types import LlmGateway, LlmRequest


def _legal_actions_summary(view_model: dict[str, Any]) -> str:
    rows: list[str] = []
    for a in view_model.get("actions") or []:
        label = str(a.get("label") or a.get("command") or "?")
        cmd = str(a.get("command") or "")
        rows.append(json.dumps({"label": label, "command": cmd}, ensure_ascii=False))
    return "\n".join(rows)


def build_tactical_prompt(view_model: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a Slay the Spire tactical agent. "
        "Reply with a single JSON object only, no markdown, with keys "
        '"command" (string, must be exactly one of the listed command strings, or null) '
        'and "rationale" (short string).'
    )
    state_block = build_tactical_state_summary(view_model)
    user = (
        "Current state (KB-enriched descriptions in hand / monsters / relics / potions / powers):\n"
        f"{state_block}\n\n"
        "Legal actions (use the exact \"command\" string):\n"
        f"{_legal_actions_summary(view_model)}\n\n"
        'Respond with: {"command": "...", "rationale": "..."}'
    )
    return system, user


def propose_from_gateway(
    view_model: dict[str, Any] | None,
    gateway: LlmGateway,
    *,
    model_hint: str | None = None,
) -> tuple[str | None, str, str | None, dict[str, Any] | None]:
    """
    Return ``(resolved_command, resolve_tag, raw_model_text, parsed_model_object)``.

    ``raw_model_text`` is the exact gateway string (for debug UI). ``parsed_model_object``
    is ``{"command": ..., "rationale": ...}`` from validated JSON when parse succeeds.
    """
    if not view_model or not view_model.get("actions"):
        return None, "no_actions", None, None
    system, user = build_tactical_prompt(view_model)
    raw = gateway.complete(LlmRequest(system=system, user=user, model=model_hint))
    try:
        proposal = parse_proposal_json(raw)
    except ValueError as e:
        return None, f"parse_error:{e}", raw, None
    parsed = {"command": proposal.command, "rationale": proposal.rationale}
    cmd, tag = resolve_to_legal_command(view_model, proposal)
    return cmd, tag, raw, parsed
