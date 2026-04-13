from __future__ import annotations

import unittest

from src.agent.tool_registry import execute_tool, list_function_tools_for_context


class TestToolRegistry(unittest.TestCase):
    def test_inspect_full_deck_lists_cards_and_truncates_long_desc(self) -> None:
        long_desc = "x" * 300
        vm = {
            "inventory": {
                "deck": [
                    {
                        "name": "Strike",
                        "type": "ATTACK",
                        "cost": 1,
                        "upgrades": 0,
                        "kb": {"description": long_desc, "type": "ATTACK"},
                    },
                    {"name": "Defend", "cost": 1, "upgrades": 1, "kb": {}},
                ]
            }
        }
        out = execute_tool("inspect_full_deck", vm, {})
        self.assertIn("## TOOL RESULT: Inspect Full Deck", out)
        self.assertIn("deck_size=2", out)
        self.assertIn("1. Strike", out)
        self.assertIn("2. Defend", out)
        self.assertIn("upgrades=1", out)
        self.assertIn("…", out)
        self.assertLess(len(out), 2000)

    def test_inspect_full_deck_exposed_for_reward_context(self) -> None:
        names = {t["name"] for t in list_function_tools_for_context("reward")}
        self.assertIn("inspect_full_deck", names)
        self.assertIn("inspect_deck_summary", names)


if __name__ == "__main__":
    unittest.main()
