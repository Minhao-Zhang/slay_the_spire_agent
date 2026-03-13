from __future__ import annotations

import json
import re
from typing import Any

from src.agent.schemas import FinalDecision, ParsedAgentTurn, ToolRequest, ValidationResult


TAG_RE = {
    "reasoning": re.compile(r"<reasoning>\s*(.*?)\s*</reasoning>", re.DOTALL | re.IGNORECASE),
    "tool_request": re.compile(r"<tool_request>\s*(.*?)\s*</tool_request>", re.DOTALL | re.IGNORECASE),
    "final_decision": re.compile(r"<final_decision>\s*(.*?)\s*</final_decision>", re.DOTALL | re.IGNORECASE),
}


def _extract_tag(raw_text: str, tag: str) -> str:
    match = TAG_RE[tag].search(raw_text or "")
    return match.group(1).strip() if match else ""


def parse_agent_output(raw_text: str) -> ParsedAgentTurn:
    reasoning = _extract_tag(raw_text, "reasoning")
    tool_request_text = _extract_tag(raw_text, "tool_request")
    final_decision_text = _extract_tag(raw_text, "final_decision")

    parsed = ParsedAgentTurn(reasoning=reasoning, response=(raw_text or "").strip())

    if tool_request_text:
        try:
            parsed.tool_request = ToolRequest.model_validate(json.loads(tool_request_text))
        except (json.JSONDecodeError, ValueError):
            pass
    if final_decision_text:
        try:
            parsed.final_decision = FinalDecision.model_validate(json.loads(final_decision_text))
        except (json.JSONDecodeError, ValueError):
            pass

    return parsed


def validate_final_decision(
    final_decision: FinalDecision | None,
    legal_actions: list[dict[str, Any]],
) -> ValidationResult:
    if not final_decision:
        return ValidationResult(valid=False, error="No final decision block returned.")

    chosen = final_decision.chosen_command.strip()
    for action in legal_actions:
        command = str(action.get("command", "")).strip()
        if chosen == command:
            return ValidationResult(
                valid=True,
                matched_command=command,
                matched_label=action.get("label"),
            )

    return ValidationResult(
        valid=False,
        error=f"Chosen command is not legal for this state: {chosen}",
    )


def inspect_pile(tool_name: str, vm: dict[str, Any]) -> list[dict[str, Any]]:
    combat = vm.get("combat") or {}
    mapping = {
        "inspect_draw_pile": combat.get("draw_pile", []),
        "inspect_discard_pile": combat.get("discard_pile", []),
        "inspect_exhaust_pile": combat.get("exhaust_pile", []),
        "InspectDrawPileTool": combat.get("draw_pile", []),
        "InspectDiscardPileTool": combat.get("discard_pile", []),
        "InspectExhaustPileTool": combat.get("exhaust_pile", []),
    }
    return mapping.get(tool_name, [])

