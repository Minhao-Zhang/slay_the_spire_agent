"""Build prompts, call gateway, parse + resolve (tactical slice)."""

from __future__ import annotations

import json
import os
from typing import Any

from src.agent_core.parse import parse_proposal_json
from src.agent_core.schemas import StructuredCommandProposal
from src.agent_core.resolve import (
    normalized_command_list,
    resolve_to_legal_command,
)
from src.agent_core.resolve_display import command_steps_for_model_output
from src.decision_engine import shortcuts
from src.domain.play_resolve import token_play_command_for_action
from src.agent_core.state_prompt import build_tactical_state_summary, optional_strategy_corpus_block
from src.agent_core.tool_registry import build_structured_tools
from src.llm_gateway.openai_chat import OpenAiChatGateway
from src.llm_gateway.types import LlmGateway, LlmRequest


def tactical_tools_enabled() -> bool:
    v = os.environ.get("SLAY_TACTICAL_TOOLS", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def max_tool_rounds() -> int:
    try:
        return max(1, min(int(os.environ.get("SLAY_MAX_TOOL_ROUNDS", "4")), 32))
    except ValueError:
        return 4

def _legal_actions_summary(view_model: dict[str, Any]) -> str:
    rows: list[str] = []
    for a in view_model.get("actions") or []:
        label = str(a.get("label") or a.get("command") or "?")
        cmd = str(a.get("command") or "")
        row: dict[str, Any] = {"label": label, "command": cmd}
        tok = a.get("card_uuid_token")
        if tok:
            row["token"] = str(tok).lower()
        rows.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(rows)


def build_tactical_prompt(view_model: dict[str, Any]) -> tuple[str, str]:
    system = (
        "You are a Slay the Spire tactical agent. "
        "Reply with a single JSON object only, no markdown, with keys "
        '"command" (string or null) and optional "commands" (non-empty array during combat; '
        "index 0 runs first, the rest queue for later ticks in the same fight), "
        'and "rationale" (short string). '
        "For **every card play** use only `PLAY <token>` with optional target index for targeted cards — "
        "copy the \"command\" value from the legal list exactly (it is already token-based). "
        "Never use numeric hand indices (`PLAY 1`, `PLAY 3 0`, …); they will be rejected. "
        "Non-card lines (END, POTION, …) use their \"command\" string as shown. "
        'Prefer either "command" or "commands", not both with conflicting intent.'
    )
    state_block = build_tactical_state_summary(view_model)
    user = (
        "Current state (KB-enriched descriptions in hand / monsters / relics / potions / powers):\n"
        f"{state_block}\n\n"
        "Legal actions (\"command\" is what you must output for that choice; card rows are PLAY <token> only):\n"
        f"{_legal_actions_summary(view_model)}\n\n"
        'Respond with: {"command": "...", "rationale": "..."} '
        'or {"commands": ["..."], "rationale": "..."}.'
    )
    user += optional_strategy_corpus_block()
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
    req = LlmRequest(system=system, user=user, model=model_hint)
    usage: dict[str, Any] = {}
    sub_calls: list[dict[str, Any]] = []
    use_tools = tactical_tools_enabled() and isinstance(gateway, OpenAiChatGateway)
    if use_tools:
        tools = build_structured_tools(view_model)
        tool_hint = (
            " You may call the provided tools to inspect draw, discard, exhaust piles, "
            "or deck summary when it helps; finish with exactly one JSON object: "
            '{"command": <string or null>, "commands": <optional array>, "rationale": <string>}. '
            "Card plays must be PLAY <token> only, never numeric indices."
        )
        raw, usage, sub_calls = gateway.complete_with_tools(
            system=system + tool_hint,
            user=user,
            tools=tools,
            max_rounds=max_tool_rounds(),
        )
    elif isinstance(gateway, OpenAiChatGateway):
        raw, usage = gateway.complete_with_usage(req)
    else:
        raw = gateway.complete(req)
    try:
        proposal = parse_proposal_json(raw)
    except ValueError as e:
        return None, f"parse_error:{e}", raw, None
    parsed: dict[str, Any] = {
        "command": proposal.command,
        "rationale": proposal.rationale,
    }
    for k, v in usage.items():
        if v is not None:
            parsed[k] = v
    if sub_calls:
        parsed["sub_calls"] = sub_calls
    cmds = normalized_command_list(proposal)
    tail: list[str] = []
    if cmds:
        tail = (
            cmds[1:]
            if shortcuts.in_fight(view_model) and len(cmds) > 1
            else []
        )
        head = StructuredCommandProposal(command=cmds[0], rationale=proposal.rationale)
        cmd, tag = resolve_to_legal_command(view_model, head)
    else:
        cmd, tag = resolve_to_legal_command(view_model, proposal)
    if proposal.commands is not None:
        parsed["commands"] = list(proposal.commands)
    if tail:
        parsed["command_queue_tail"] = tail
    step_cmds = cmds if cmds else []
    if view_model and step_cmds:
        parsed["command_steps"] = command_steps_for_model_output(
            view_model,
            step_cmds,
            rationale=proposal.rationale,
        )
        if cmd:
            parsed["command_canonical"] = cmd
    return cmd, tag, raw, parsed
