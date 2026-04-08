from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.agent.config import AgentConfig
from src.agent.planning import resolve_planning
from src.agent.schemas import AgentTrace
from src.agent.session_state import TurnConversation


def _minimal_trace() -> AgentTrace:
    return AgentTrace(
        decision_id="d1",
        state_id="s1",
        turn_key="MAP:5",
        timestamp="2020-01-01T00:00:00+00:00",
        status="building_prompt",
        agent_mode="propose",
    )


class TestResolvePlanning(unittest.TestCase):
    def test_non_combat_map_heuristic_when_planner_enabled(self) -> None:
        session = TurnConversation()
        trace = _minimal_trace()
        cfg = AgentConfig().model_copy(update={"planner_enabled": True})
        vm = {
            "header": {"floor": 5, "class": "Ironclad"},
            "screen": {"type": "MAP"},
            "actions": [{"label": "a", "command": "x"}],
        }
        out = resolve_planning(
            vm,
            trace,
            session,
            cfg,
            llm=None,
            ai_enabled=False,
            emit_trace=lambda: None,
        )
        self.assertIsNotNone(out.non_combat_plan_block)
        assert out.non_combat_plan_block is not None
        self.assertIn("## TURN PLAN", out.non_combat_plan_block)
        self.assertIn("pathing", out.non_combat_plan_block.lower())
        self.assertIn("screen=MAP", trace.planner_summary)

    def test_non_combat_no_block_when_planner_disabled(self) -> None:
        session = TurnConversation()
        trace = _minimal_trace()
        cfg = AgentConfig().model_copy(update={"planner_enabled": False})
        vm = {
            "header": {"floor": 5},
            "screen": {"type": "MAP"},
            "actions": [],
        }
        out = resolve_planning(
            vm,
            trace,
            session,
            cfg,
            llm=None,
            ai_enabled=False,
            emit_trace=lambda: None,
        )
        self.assertIsNone(out.non_combat_plan_block)

    def test_combat_calls_llm_and_sets_plan(self) -> None:
        session = TurnConversation()
        trace = _minimal_trace()
        cfg = AgentConfig().model_copy(update={"planner_enabled": True})
        llm = MagicMock()
        llm.generate_combat_plan.return_value = {
            "raw_output": "## Win condition\nKill cultist.",
            "latency_ms": 10,
            "token_usage": None,
        }
        vm = {
            "header": {"floor": 3, "turn": 1, "class": "Ironclad"},
            "screen": {"type": "COMBAT"},
            "combat": {
                "monsters": [{"name": "Cultist", "is_gone": False, "max_hp": 48}],
                "hand": [],
                "player_block": 0,
            },
            "inventory": {"relics": [], "potions": []},
        }
        out = resolve_planning(
            vm,
            trace,
            session,
            cfg,
            llm=llm,
            ai_enabled=True,
            emit_trace=lambda: None,
        )
        self.assertTrue(out.combat_plan_updated)
        self.assertIn("Kill cultist", session.combat_plan_guide)
        self.assertIsNone(out.non_combat_plan_block)
        self.assertIn("COMBAT", trace.planner_summary)
        llm.generate_combat_plan.assert_called_once()

    def test_combat_skips_llm_when_planner_disabled(self) -> None:
        session = TurnConversation()
        trace = _minimal_trace()
        cfg = AgentConfig().model_copy(update={"planner_enabled": False})
        llm = MagicMock()
        vm = {
            "header": {"floor": 3, "turn": 1},
            "screen": {"type": "COMBAT"},
            "combat": {
                "monsters": [{"name": "Cultist", "is_gone": False, "max_hp": 48}],
                "hand": [],
                "player_block": 0,
            },
        }
        resolve_planning(
            vm,
            trace,
            session,
            cfg,
            llm=llm,
            ai_enabled=True,
            emit_trace=lambda: None,
        )
        llm.generate_combat_plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
