from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from src.agent.tracing import combat_encounter_fingerprint


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
    strategy_memory: dict[str, str] = field(
        default_factory=lambda: {
            "deck_plan": "",
            "pathing_goal": "",
            "boss_prep": "",
            "constraints": "",
        }
    )
    compaction_count: int = 0
    combat_plan_guide: str = ""
    combat_plan_fingerprint: str | None = None

    def sync_combat_plan_for_vm(self, vm: dict) -> None:
        """Drop cached combat plan when leaving combat or when the encounter changes."""
        fp = combat_encounter_fingerprint(vm)
        if fp is None:
            self.combat_plan_guide = ""
            self.combat_plan_fingerprint = None
            return
        if self.combat_plan_fingerprint != fp:
            self.combat_plan_guide = ""
            self.combat_plan_fingerprint = None

    def set_combat_plan(self, guide: str, fingerprint: str) -> None:
        self.combat_plan_guide = (guide or "").strip()
        self.combat_plan_fingerprint = fingerprint

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

    def update_strategy_memory(self, vm: dict) -> None:
        inventory = vm.get("inventory") or {}
        deck = inventory.get("deck") or []
        type_counts: dict[str, int] = {}
        for card in deck:
            card_type = ((card.get("kb") or {}).get("type") or card.get("type") or "").upper()
            if not card_type:
                continue
            type_counts[card_type] = type_counts.get(card_type, 0) + 1

        if type_counts:
            dominant_type = max(type_counts.items(), key=lambda item: item[1])[0]
            self.strategy_memory["deck_plan"] = (
                f"Deck leans toward {dominant_type}; keep picks/upgrades coherent with this axis."
            )

        header = vm.get("header") or {}
        floor = header.get("floor")
        hp_display = str(header.get("hp_display", ""))
        hp_ratio = 1.0
        if "/" in hp_display:
            try:
                cur, max_hp = hp_display.split("/", 1)
                hp_ratio = max(0.0, min(1.0, int(cur) / max(1, int(max_hp))))
            except ValueError:
                hp_ratio = 1.0

        screen = vm.get("screen") or {}
        if screen.get("type") == "MAP":
            if hp_ratio < 0.45:
                self.strategy_memory["pathing_goal"] = "Prefer safer pathing with rest sites and avoid risky elite chains."
            else:
                self.strategy_memory["pathing_goal"] = "Take high-value pathing when deck can handle elites."

        map_state = vm.get("map") or {}
        boss_name = map_state.get("boss_name")
        if boss_name:
            self.strategy_memory["boss_prep"] = f"Prepare for upcoming boss: {boss_name}."

        combat = vm.get("combat") or {}
        powers = combat.get("player_powers") or []
        if any(str(p.get("name", "")).lower() == "no draw" for p in powers):
            self.strategy_memory["constraints"] = "Current turn has draw constraint (No Draw); avoid draw-dependent lines."

    def strategy_memory_lines(self) -> list[str]:
        lines: list[str] = []
        for key in ("deck_plan", "pathing_goal", "boss_prep", "constraints"):
            value = self.strategy_memory.get(key, "").strip()
            if value:
                lines.append(f"{key}: {value}")
        return lines

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

