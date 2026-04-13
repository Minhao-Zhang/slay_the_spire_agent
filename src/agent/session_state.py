from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import tiktoken

from src.agent.tracing import combat_encounter_fingerprint
from src.agent.vm_shapes import normalize_legal_actions


def _tiktoken_encoding_for_model(model_name: str) -> tiktoken.Encoding:
    name = (model_name or "").strip() or "gpt-4o"
    try:
        return tiktoken.encoding_for_model(name)
    except KeyError:
        try:
            return tiktoken.encoding_for_model("gpt-4o")
        except KeyError:
            return tiktoken.get_encoding("o200k_base")


def count_tokens_system_and_history(
    system_prompt: str,
    messages: list[dict[str, Any]],
    tokenizer_model: str,
) -> int:
    """Approximate chat input tokens (system + messages) for compaction gating.

    Uses tiktoken with the same per-message overhead pattern as OpenAI chat docs;
    provider billed prompt_tokens may still differ slightly (tools, merges, etc.).
    """
    enc = _tiktoken_encoding_for_model(tokenizer_model)
    total = 0
    chain: list[dict[str, Any]] = [{"role": "system", "content": system_prompt or ""}, *messages]
    for msg in chain:
        role = str(msg.get("role", "") or "")
        content = str(msg.get("content", "") or "")
        total += 4
        total += len(enc.encode(role))
        total += len(enc.encode(content))
    total += 2
    return total


def estimate_message_tokens(message: dict[str, str]) -> int:
    content = str(message.get("content", "") or "")
    role = str(message.get("role", "") or "")
    # Cheap approximation: ~4 chars/token plus a small per-message overhead.
    return max(1, (len(content) + len(role) + 3) // 4) + 8


def format_executed_action(action: str, legal_actions: list[dict[str, str]] | None) -> str:
    normalized = action.strip()
    for candidate in normalize_legal_actions(legal_actions or []):
        command = str(candidate.get("command", "")).strip()
        if command != normalized:
            continue
        label = str(candidate.get("label", "")).strip()
        return f"{label} | {command}" if label else command
    return normalized


def is_command_failure_state(state: dict) -> str:
    error = (state or {}).get("error")
    if not isinstance(error, str):
        return ""
    return error.strip()


def mark_trace_command_failed(trace, error_message: str, action: str):
    updated = deepcopy(trace)
    updated.status = "invalid"
    updated.approval_status = "error"
    updated.error = f"Executed command failed: {error_message}"
    updated.execution_outcome = "command_failed"
    updated.final_decision = action
    updated.update_seq += 1
    return updated


@dataclass
class TurnConversation:
    scene_key: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)
    action_history: list[str] = field(default_factory=list)
    strategy_notes: dict[str, str] = field(
        default_factory=lambda: {
            "deck_trajectory": "",
            "pathing_intent": "",
            "threat_assessment": "",
            "resource_plan": "",
        }
    )
    compaction_count: int = 0
    combat_plan_guide: str = ""
    combat_plan_fingerprint: str | None = None
    combat_plan_last_turn: int | None = None
    _last_seen_act: int | None = field(default=None, repr=False)

    def sync_combat_plan_for_vm(self, vm: dict) -> None:
        """Drop cached combat plan when leaving combat or when the encounter changes."""
        fp = combat_encounter_fingerprint(vm)
        if fp is None:
            self.combat_plan_guide = ""
            self.combat_plan_fingerprint = None
            self.combat_plan_last_turn = None
            return
        if self.combat_plan_fingerprint != fp:
            self.combat_plan_guide = ""
            self.combat_plan_fingerprint = None
            self.combat_plan_last_turn = None

    def set_combat_plan(self, guide: str, fingerprint: str, turn: int | None = None) -> None:
        self.combat_plan_guide = (guide or "").strip()
        self.combat_plan_fingerprint = fingerprint
        self.combat_plan_last_turn = turn

    def set_scene(self, scene_key: str) -> None:
        if self.scene_key == scene_key:
            return
        self.scene_key = scene_key
        self.action_history.clear()

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def remember_action(self, action: str) -> None:
        self.action_history.append(action)

    def update_strategy_notes(self, notes: dict[str, str]) -> None:
        for key, value in notes.items():
            if not value or not str(value).strip():
                continue
            self.strategy_notes[str(key)] = str(value).strip()

    def strategy_notes_lines(self) -> list[str]:
        lines: list[str] = []
        for key in ("deck_trajectory", "pathing_intent", "threat_assessment", "resource_plan"):
            value = self.strategy_notes.get(key, "").strip()
            if value:
                lines.append(f"{key}: {value}")
        return lines

    def estimated_token_count(self) -> int:
        return sum(estimate_message_tokens(message) for message in self.messages)

    def needs_compaction(self, token_threshold: int, system_prompt: str, tokenizer_model: str) -> bool:
        if token_threshold <= 0:
            return False
        return count_tokens_system_and_history(system_prompt, self.messages, tokenizer_model) > token_threshold

    def compact_history(self, summary: str, keep_recent: int) -> None:
        if not summary:
            return

        keep_recent = max(0, keep_recent)
        recent_messages = self.messages[-keep_recent:] if keep_recent else []
        compacted_summary = {
            "role": "user",
            "content": f"## COMPACTED HISTORY\n{summary.strip()}",
        }
        self.messages = [compacted_summary, *recent_messages]
        self.compaction_count += 1

    def compact_history_fallback(self, keep_recent: int) -> None:
        """If summarization fails, keep only the recent tail and a short stub (bounded history)."""
        keep_recent = max(0, keep_recent)
        recent_messages = self.messages[-keep_recent:] if keep_recent else []
        stub = {
            "role": "user",
            "content": "## COMPACTED HISTORY\n(Prior turns dropped: summarization failed or returned empty.)",
        }
        self.messages = [stub, *recent_messages]
        self.compaction_count += 1

