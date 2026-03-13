from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TurnConversation:
    turn_key: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)
    action_history: list[str] = field(default_factory=list)

    def reset_for_turn(self, turn_key: str) -> None:
        if self.turn_key == turn_key:
            return
        self.turn_key = turn_key
        self.messages.clear()
        self.action_history.clear()

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def remember_action(self, action: str) -> None:
        self.action_history.append(action)

