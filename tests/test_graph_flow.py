from __future__ import annotations

import unittest

from src.agent.graph import SpireDecisionAgent


class TestGraphFlow(unittest.TestCase):
    def test_prompt_pipeline_nodes_without_plan_turn(self) -> None:
        agent = SpireDecisionAgent()
        nodes = list(agent.graph.get_graph().nodes.keys())
        self.assertIn("retrieve_memory", nodes)
        self.assertIn("resolve_planning", nodes)
        self.assertIn("assemble_prompt", nodes)
        self.assertNotIn("plan_turn", nodes)


if __name__ == "__main__":
    unittest.main()
