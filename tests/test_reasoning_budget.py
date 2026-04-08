from __future__ import annotations

import unittest

from src.agent.config import AgentConfig
from src.agent.reasoning_budget import ReasoningBudgetRouter


class TestReasoningBudgetRouter(unittest.TestCase):
    def test_legacy_matches_combat_non_combat_slots(self) -> None:
        cfg = AgentConfig().model_copy(
            update={
                "reasoning_budget_enabled": False,
                "combat_turn_llm": "reasoning",
                "non_combat_turn_llm": "fast",
            }
        )
        r = ReasoningBudgetRouter(cfg)
        c = r.resolve({"combat": {"monsters": []}, "header": {}, "screen": {}})
        self.assertEqual(c.model_key, "reasoning")
        nc = r.resolve({"header": {}, "screen": {"type": "MAP"}})
        self.assertEqual(nc.model_key, "fast")

    def test_enabled_map_uses_reasoning_and_full_retrieval(self) -> None:
        cfg = AgentConfig().model_copy(update={"reasoning_budget_enabled": True})
        r = ReasoningBudgetRouter(cfg)
        p = r.resolve({"header": {"floor": 5}, "screen": {"type": "MAP"}, "actions": []})
        self.assertEqual(p.name, "map_pathing")
        self.assertEqual(p.model_key, "reasoning")
        self.assertEqual(p.retrieval_mode, "full")
        self.assertEqual(p.tool_filter, "map")

    def test_enabled_boss_combat_uses_reasoning(self) -> None:
        cfg = AgentConfig().model_copy(
            update={"reasoning_budget_enabled": True, "combat_turn_llm": "fast"}
        )
        r = ReasoningBudgetRouter(cfg)
        vm = {
            "combat": {
                "monsters": [{"name": "The Guardian", "is_gone": False, "max_hp": 200}],
                "hand": [],
            },
            "header": {"floor": 10},
            "screen": {"type": "COMBAT"},
        }
        p = r.resolve(vm)
        self.assertEqual(p.name, "combat_boss_or_elite")
        self.assertEqual(p.model_key, "reasoning")
        self.assertEqual(p.retrieval_mode, "full")


if __name__ == "__main__":
    unittest.main()
