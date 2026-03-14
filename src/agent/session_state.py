from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


def estimate_message_tokens(message: dict[str, str]) -> int:
    content = str(message.get("content", "") or "")
    role = str(message.get("role", "") or "")
    # Cheap approximation: ~4 chars/token plus a small per-message overhead.
    return max(1, (len(content) + len(role) + 3) // 4) + 8


def format_executed_action(action: str, legal_actions: list[dict[str, str]] | None) -> str:
    normalized = action.strip()
    for candidate in legal_actions or []:
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
    compaction_count: int = 0

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

    def estimated_token_count(self) -> int:
        return sum(estimate_message_tokens(message) for message in self.messages)

    def needs_compaction(self, token_threshold: int) -> bool:
        return token_threshold > 0 and self.estimated_token_count() > token_threshold

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

