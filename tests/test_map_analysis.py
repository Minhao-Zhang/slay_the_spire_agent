from __future__ import annotations

import unittest

from src.agent.map_analysis import analyze_map_paths
from src.agent.prompt_builder import _map_planning_lines


def _node(x: int, y: int, symbol: str, children: list[tuple[int, int]]) -> dict:
    return {
        "x": x,
        "y": y,
        "symbol": symbol,
        "children": [{"x": cx, "y": cy} for cx, cy in children],
    }


class TestAnalyzeMapPaths(unittest.TestCase):
    def test_linear_single_path_to_bottom(self) -> None:
        nodes = [
            _node(0, 0, "M", [(0, 1)]),
            _node(0, 1, "E", [(0, 2)]),
            _node(0, 2, "R", []),
        ]
        next_nodes = [{"x": 0, "y": 0, "symbol": "M"}]
        out = analyze_map_paths(nodes, None, next_nodes, False)
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual(a["path_count"], 1)
        self.assertEqual(a["sample_path"], ["M", "E", "R"])
        self.assertEqual(a["encounter_summary"].get("monster"), 1)
        self.assertEqual(a["encounter_summary"].get("elite"), 1)
        self.assertEqual(a["encounter_summary"].get("rest"), 1)
        self.assertIn("elite→rest", a["notable_sequences"])

    def test_branching_prefers_path_with_fewer_elites_when_same_rests(self) -> None:
        """Two routes to goal: M-E-R vs M-M-R — sample picks M-M-R (tie on R, fewer E)."""
        nodes = [
            _node(0, 0, "M", [(0, 1), (1, 1)]),
            _node(0, 1, "E", [(0, 2)]),
            _node(1, 1, "M", [(0, 2)]),
            _node(0, 2, "R", []),
        ]
        next_nodes = [{"x": 0, "y": 0, "symbol": "M"}]
        out = analyze_map_paths(nodes, None, next_nodes, False)
        self.assertEqual(len(out), 1)
        a = out[0]
        self.assertEqual(a["path_count"], 2)
        self.assertEqual(a["sample_path"], ["M", "M", "R"])
        # Mean counts across two paths: monsters 1+2, elite 1+0, rest 1+1
        self.assertEqual(a["encounter_summary"].get("monster"), 2)
        self.assertEqual(a["encounter_summary"].get("elite"), 1)
        self.assertEqual(a["encounter_summary"].get("rest"), 1)

    def test_two_next_nodes_separate_analyses(self) -> None:
        """Fork from row 0: left and right both lead to same goal with one path each."""
        nodes = [
            _node(0, 0, "M", [(0, 1)]),
            _node(1, 0, "M", [(1, 1)]),
            _node(0, 1, "R", [(0, 2)]),
            _node(1, 1, "M", [(0, 2)]),
            _node(0, 2, "E", []),
        ]
        next_nodes = [
            {"x": 0, "y": 0, "symbol": "M"},
            {"x": 1, "y": 0, "symbol": "M"},
        ]
        out = analyze_map_paths(nodes, None, next_nodes, False)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["path_count"], 1)
        self.assertEqual(out[0]["sample_path"], ["M", "R", "E"])
        self.assertEqual(out[1]["path_count"], 1)
        self.assertEqual(out[1]["sample_path"], ["M", "M", "E"])

    def test_empty_next_nodes_returns_empty(self) -> None:
        nodes = [_node(0, 0, "M", [])]
        self.assertEqual(analyze_map_paths(nodes, None, [], False), [])

    def test_unknown_next_node_emits_zero_paths(self) -> None:
        nodes = [_node(0, 0, "M", [])]
        out = analyze_map_paths(nodes, None, [{"x": 9, "y": 9, "symbol": "?"}], False)
        self.assertEqual(out[0]["path_count"], 0)
        self.assertEqual(out[0]["sample_path"], [])

    def test_map_planning_lines_include_path_analysis(self) -> None:
        nodes = [
            _node(0, 0, "M", [(0, 1)]),
            _node(0, 1, "E", [(0, 2)]),
            _node(0, 2, "R", []),
        ]
        vm = {
            "header": {"floor": 1},
            "screen": {"type": "MAP"},
            "map": {
                "nodes": nodes,
                "current_node": None,
                "next_nodes": [{"x": 0, "y": 0, "symbol": "M"}],
                "boss_available": False,
            },
        }
        lines = _map_planning_lines(vm)
        joined = "\n".join(lines)
        self.assertIn("## Path analysis", joined)
        self.assertIn("routes to boss row", joined)
        self.assertIn("M → E → R", joined)


if __name__ == "__main__":
    unittest.main()
