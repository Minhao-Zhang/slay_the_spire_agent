"""Context-based model slot, reasoning effort, retrieval mode, and tool filtering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agent.config import AgentConfig
from src.agent.vm_shapes import as_dict

_BOSS_SUBSTRINGS = (
    "boss",
    "heart",
    "donu",
    "deca",
    "awakened",
    "time eater",
    "champ",
    "collector",
    "automaton",
    "guardian",
    "slaver",
)


def _effort_for_model_key(config: AgentConfig, model_key: str) -> str:
    if (model_key or "reasoning").strip().lower() == "fast":
        return (config.fast_reasoning_effort or "none").strip().lower()
    return (config.reasoning_effort or "medium").strip().lower()


def _infer_act(floor: int | None, header_act: Any = None) -> int:
    if isinstance(header_act, int) and header_act >= 1:
        return header_act
    if isinstance(header_act, str) and header_act.strip().isdigit():
        try:
            a = int(header_act.strip())
            if a >= 1:
                return a
        except ValueError:
            pass
    if floor is None or floor < 1:
        return 1
    if floor <= 17:
        return 1
    if floor <= 33:
        return 2
    return 3


def _floor_int(header: dict[str, Any]) -> int | None:
    f = header.get("floor")
    if isinstance(f, int):
        return f
    if isinstance(f, str) and f.strip().lstrip("-").isdigit():
        try:
            return int(f.strip())
        except ValueError:
            return None
    return None


def _header_turn(header: dict[str, Any]) -> int | None:
    t = header.get("turn")
    if isinstance(t, int):
        return t
    if isinstance(t, str) and t.strip().isdigit():
        return int(t.strip())
    return None


def _combat_looks_high_stakes(vm: dict[str, Any]) -> bool:
    combat = vm.get("combat")
    if not isinstance(combat, dict):
        return False
    for m in combat.get("monsters") or []:
        if not isinstance(m, dict) or m.get("is_gone"):
            continue
        name = str(m.get("name", "")).lower()
        if any(s in name for s in _BOSS_SUBSTRINGS):
            return True
        try:
            mh = int(m.get("max_hp", 0) or 0)
        except (TypeError, ValueError):
            mh = 0
        if mh >= 200:
            return True
    return False


def _event_option_count(vm: dict[str, Any]) -> int:
    screen = as_dict(vm.get("screen"))
    if screen.get("type") != "EVENT":
        return 0
    content = as_dict(screen.get("content"))
    opts = content.get("options")
    if isinstance(opts, list):
        return len(opts)
    cl = content.get("choice_list")
    if isinstance(cl, list):
        return len(cl)
    return 0


def _combat_reward_has_card(vm: dict[str, Any]) -> bool:
    screen = as_dict(vm.get("screen"))
    if screen.get("type") != "COMBAT_REWARD":
        return False
    content = as_dict(screen.get("content"))
    for r in content.get("rewards") or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("reward_type", "")).upper() == "CARD":
            return True
    return False


@dataclass(frozen=True, slots=True)
class ReasoningProfile:
    name: str
    model_key: str
    reasoning_effort: str
    retrieval_mode: str = "tag_match"
    tool_filter: str | None = None
    description: str = ""


class ReasoningBudgetRouter:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def resolve(self, vm: dict[str, Any]) -> ReasoningProfile:
        if not self._config.reasoning_budget_enabled:
            return self._legacy_profile(vm)

        header = as_dict(vm.get("header"))
        screen = as_dict(vm.get("screen"))
        floor = _floor_int(header)
        act = _infer_act(floor, header.get("act"))
        screen_type = str(screen.get("type", "NONE") or "NONE").upper()
        turn = _header_turn(header)

        if screen_type == "GAME_OVER":
            return ReasoningProfile(
                name="game_over",
                model_key="fast",
                reasoning_effort=_effort_for_model_key(self._config, "fast"),
                retrieval_mode="skip",
                tool_filter=None,
                description="Game over screen; no retrieval",
            )

        if vm.get("combat"):
            if _combat_looks_high_stakes(vm):
                return ReasoningProfile(
                    name="combat_boss_or_elite",
                    model_key="reasoning",
                    reasoning_effort=_effort_for_model_key(self._config, "reasoning"),
                    retrieval_mode="full",
                    tool_filter="combat",
                    description="Boss / elite / high-HP combat",
                )
            if turn is None or turn <= 1:
                return ReasoningProfile(
                    name="combat_hallway_turn_one",
                    model_key="fast",
                    reasoning_effort=_effort_for_model_key(self._config, "fast"),
                    retrieval_mode="tag_match",
                    tool_filter="combat",
                    description="Hallway combat first turn",
                )
            return ReasoningProfile(
                name="combat_hallway_followup",
                model_key="fast",
                reasoning_effort=_effort_for_model_key(self._config, "fast"),
                retrieval_mode="reuse",
                tool_filter="combat",
                description="Hallway combat turn 2+",
            )

        if screen_type == "MAP":
            return ReasoningProfile(
                name="map_pathing",
                model_key="reasoning",
                reasoning_effort=_effort_for_model_key(self._config, "reasoning"),
                retrieval_mode="full",
                tool_filter="map",
                description="Map pathing decisions",
            )

        if screen_type == "COMBAT_REWARD":
            if _combat_reward_has_card(vm) and act == 1:
                return ReasoningProfile(
                    name="reward_act1_card",
                    model_key="reasoning",
                    reasoning_effort=_effort_for_model_key(self._config, "reasoning"),
                    retrieval_mode="full",
                    tool_filter="reward",
                    description="Act 1 card reward",
                )
            if _combat_reward_has_card(vm) and act >= 3:
                return ReasoningProfile(
                    name="reward_act3_card",
                    model_key="fast",
                    reasoning_effort=_effort_for_model_key(self._config, "fast"),
                    retrieval_mode="tag_match",
                    tool_filter="reward",
                    description="Act 3 card reward",
                )
            return ReasoningProfile(
                name="reward_simple",
                model_key="fast",
                reasoning_effort=_effort_for_model_key(self._config, "fast"),
                retrieval_mode="skip",
                tool_filter="reward",
                description="Simple combat reward (gold / single pick)",
            )

        if screen_type == "SHOP":
            return ReasoningProfile(
                name="shop",
                model_key="fast",
                reasoning_effort=_effort_for_model_key(self._config, "fast"),
                retrieval_mode="tag_match",
                tool_filter="reward",
                description="Shop screen",
            )

        if screen_type == "EVENT":
            n = _event_option_count(vm)
            if n >= 3:
                return ReasoningProfile(
                    name="event_complex",
                    model_key="reasoning",
                    reasoning_effort=_effort_for_model_key(self._config, "reasoning"),
                    retrieval_mode="full",
                    tool_filter="event",
                    description="Event with many options",
                )
            return ReasoningProfile(
                name="event_simple",
                model_key="fast",
                reasoning_effort=_effort_for_model_key(self._config, "fast"),
                retrieval_mode="tag_match",
                tool_filter="event",
                description="Simple event",
            )

        if screen_type == "REST":
            return ReasoningProfile(
                name="rest_site",
                model_key="fast",
                reasoning_effort=_effort_for_model_key(self._config, "fast"),
                retrieval_mode="tag_match",
                tool_filter="reward",
                description="Rest site",
            )

        mk = self._config.non_combat_turn_llm
        return ReasoningProfile(
            name="non_combat_fallback",
            model_key=mk,
            reasoning_effort=_effort_for_model_key(self._config, mk),
            retrieval_mode="tag_match",
            tool_filter=None,
            description="Default non-combat routing",
        )

    def _legacy_profile(self, vm: dict[str, Any]) -> ReasoningProfile:
        mk = self._config.combat_turn_llm if vm.get("combat") else self._config.non_combat_turn_llm
        effort = _effort_for_model_key(self._config, mk)
        return ReasoningProfile(
            name="legacy_binary",
            model_key=mk,
            reasoning_effort=effort,
            retrieval_mode="tag_match",
            tool_filter=None,
            description="Matches pre-router combat vs non-combat switch",
        )
