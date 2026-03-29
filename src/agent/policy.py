from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from src.agent.schemas import FinalDecision, ParsedAgentTurn, ToolRequest, ValidationResult
from src.agent.tool_registry import canonical_tool_name
from src.agent.vm_shapes import normalize_legal_actions


TAG_RE = {
    "reasoning": re.compile(r"<reasoning>\s*(.*?)\s*</reasoning>", re.DOTALL | re.IGNORECASE),
    "tool_request": re.compile(r"<tool_request>\s*(.*?)\s*</tool_request>", re.DOTALL | re.IGNORECASE),
    "final_decision": re.compile(r"<final_decision>\s*(.*?)\s*</final_decision>", re.DOTALL | re.IGNORECASE),
}


def _extract_tag(raw_text: str, tag: str) -> str:
    match = TAG_RE[tag].search(raw_text or "")
    return match.group(1).strip() if match else ""


def _strip_markdown_fences(blob: str) -> str:
    """Remove optional ``` / ```json fences around JSON inside a tag."""
    s = (blob or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _slice_balanced_json_object(s: str, start: int = 0) -> str:
    """Return the first {...} span with balanced braces starting at s[start], or ""."""
    n = len(s)
    i = start
    while i < n and s[i] != "{":
        i += 1
    if i >= n:
        return ""
    depth = 0
    for j in range(i, n):
        c = s[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i : j + 1]
    return ""


_FINAL_DECISION_OPEN_RE = re.compile(r"<final_decision>\s*", re.IGNORECASE | re.DOTALL)


def _final_decision_json_candidates(raw_text: str) -> list[str]:
    """Collect JSON blobs to try: closed tags (last first), then truncated open-tag + JSON."""
    text = raw_text or ""
    candidates: list[str] = []

    closed_bodies = [m.group(1).strip() for m in TAG_RE["final_decision"].finditer(text)]
    for body in reversed(closed_bodies):
        candidates.append(_strip_markdown_fences(body))

    # Truncated stream: <final_decision> with JSON but no </final_decision> (common at low max tokens).
    last_open = None
    for m in _FINAL_DECISION_OPEN_RE.finditer(text):
        last_open = m
    if last_open:
        tail = text[last_open.end() :]
        low_tail = tail.lower()
        if "</final_decision>" in low_tail:
            end = low_tail.index("</final_decision>")
            tail = tail[:end]
        tail = tail.strip()
        tail = _strip_markdown_fences(tail)
        extracted = _slice_balanced_json_object(tail, 0)
        if extracted:
            candidates.append(extracted)

    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _parse_final_decision_blob(blob: str) -> FinalDecision | None:
    blob = (blob or "").strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    try:
        return FinalDecision.model_validate(data)
    except ValidationError:
        return None


def parse_agent_output(raw_text: str) -> ParsedAgentTurn:
    reasoning = _extract_tag(raw_text, "reasoning")
    tool_request_text = _extract_tag(raw_text, "tool_request")

    parsed = ParsedAgentTurn(reasoning=reasoning, response=(raw_text or "").strip())

    if tool_request_text:
        try:
            parsed.tool_request = ToolRequest.model_validate(json.loads(tool_request_text))
        except (json.JSONDecodeError, ValueError, ValidationError):
            pass

    for blob in _final_decision_json_candidates(raw_text):
        fd = _parse_final_decision_blob(blob)
        if fd is not None:
            parsed.final_decision = fd
            break

    return parsed


_PLAY_TOKEN_RE = re.compile(r"^PLAY\s+([A-Za-z0-9]{6})(?:\s+(\d+))?$", re.IGNORECASE)


def _is_numeric_play(command: str) -> bool:
    """Return True if command is already a canonical numeric PLAY (PLAY <int> [<int>]).

    Hand indices are 1-based and at most 2 digits (max ~10 cards in hand),
    so a 6-digit numeric string like '033229' is a UUID token, not a hand index.
    """
    parts = command.strip().upper().split()
    return len(parts) >= 2 and parts[0] == "PLAY" and parts[1].isdigit() and len(parts[1]) <= 2


def resolve_token_play(
    command: str,
    legal_actions: list[dict[str, Any]],
) -> str | None:
    """Resolve a token-based PLAY command to the canonical numeric command.

    Returns the canonical command string if found, else None.
    Works with: PLAY <token> or PLAY <token> <target_index>
    """
    legal_actions = normalize_legal_actions(legal_actions)

    m = _PLAY_TOKEN_RE.match(command.strip())
    if not m:
        return None
    token = m.group(1).lower()
    target_index = int(m.group(2)) if m.group(2) is not None else None

    for action in legal_actions:
        cmd = str(action.get("command", ""))
        if not cmd.upper().startswith("PLAY "):
            continue
        act_token = (action.get("card_uuid_token") or "").lower()
        if act_token != token:
            continue
        if target_index is None:
            # Untargeted: action must not have monster_index
            if "monster_index" not in action:
                return cmd
        else:
            # Targeted: monster_index must match
            if action.get("monster_index") == target_index:
                return cmd
    return None


def is_end_turn_command_token(cmd: str) -> bool:
    """True if this string is the end-turn command (``END``), ignoring case/extra spaces."""
    return " ".join((cmd or "").strip().upper().split()) == "END"


def end_turn_must_be_standalone_error(commands: list[str]) -> str | None:
    """If END appears in a multi-command list, return an error message; else None."""
    raw = [str(c).strip() for c in commands if str(c).strip()]
    if len(raw) <= 1:
        return None
    if any(is_end_turn_command_token(c) for c in raw):
        return (
            "END (end turn) must be the only entry in chosen_commands — never queue END with "
            "other commands. List only card/potion/other plays here; after they execute and the "
            "state refreshes, output a new <final_decision> with chosen_commands:[\"END\"] alone."
        )
    return None


def validate_final_decision(
    final_decision: FinalDecision | None,
    legal_actions: list[dict[str, Any]],
) -> ValidationResult:
    legal_actions = normalize_legal_actions(legal_actions)
    if not final_decision:
        return ValidationResult(valid=False, error="No final decision block returned.")

    def _norm(value: str) -> str:
        return " ".join((value or "").strip().split()).lower()

    # Validate the first command in the sequence
    commands = final_decision.chosen_commands
    if not commands:
        return ValidationResult(valid=False, error="chosen_commands is empty.")

    end_err = end_turn_must_be_standalone_error(commands)
    if end_err:
        return ValidationResult(valid=False, error=end_err)

    chosen = str(commands[0]).strip()
    by_command = {_norm(str(action.get("command", ""))): action for action in legal_actions}
    by_label = {_norm(str(action.get("label", ""))): action for action in legal_actions}

    # 1) Token-based PLAY resolution (new primary path for card plays).
    if chosen.upper().startswith("PLAY ") and not _is_numeric_play(chosen):
        resolved = resolve_token_play(chosen, legal_actions)
        if resolved:
            action = by_command.get(_norm(resolved))
            return ValidationResult(
                valid=True,
                matched_command=resolved,
                matched_label=action.get("label") if action else None,
            )
        return ValidationResult(
            valid=False,
            error=f"Token-based PLAY command could not be resolved against current hand: {chosen!r}",
        )

    # 2) Strict command match (with whitespace/case normalization).
    if _norm(chosen) in by_command:
        action = by_command[_norm(chosen)]
        return ValidationResult(
            valid=True,
            matched_command=str(action.get("command", "")).strip(),
            matched_label=action.get("label"),
        )

    # 3) Label-based intent resolution when model cannot emit exact command.
    chosen_label = str(final_decision.chosen_label or "").strip()
    if _norm(chosen_label) in by_label:
        action = by_label[_norm(chosen_label)]
        return ValidationResult(
            valid=True,
            matched_command=str(action.get("command", "")).strip(),
            matched_label=action.get("label"),
        )

    # 4) Action type + choice index fallback for choose-style screens.
    action_type = _norm(final_decision.action_type)
    if action_type == "choose" and isinstance(final_decision.choice_index, int):
        expected = f"choose {final_decision.choice_index}"
        if _norm(expected) in by_command:
            action = by_command[_norm(expected)]
            return ValidationResult(
                valid=True,
                matched_command=str(action.get("command", "")).strip(),
                matched_label=action.get("label"),
            )

    return ValidationResult(
        valid=False,
        error=(
            "Could not resolve a legal action from model output. "
            f"chosen_commands[0]={chosen!r}, chosen_label={chosen_label!r}, "
            f"action_type={final_decision.action_type!r}, choice_index={final_decision.choice_index!r}"
        ),
    )


def inspect_pile(tool_name: str, vm: dict[str, Any]) -> list[dict[str, Any]]:
    combat = vm.get("combat") or {}
    name = canonical_tool_name(tool_name)
    mapping = {
        "inspect_draw_pile": combat.get("draw_pile", []),
        "inspect_discard_pile": combat.get("discard_pile", []),
        "inspect_exhaust_pile": combat.get("exhaust_pile", []),
        "InspectDrawPileTool": combat.get("draw_pile", []),
        "InspectDiscardPileTool": combat.get("discard_pile", []),
        "InspectExhaustPileTool": combat.get("exhaust_pile", []),
    }
    return mapping.get(name, [])

