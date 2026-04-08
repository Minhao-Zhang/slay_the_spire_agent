from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.agent.reflection import RunAnalyzer


class TestRunAnalyzer(unittest.TestCase):
    def test_analyze_counts_ai_json_and_reads_snapshot(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "0001.ai.json").write_text(
                json.dumps(
                    {
                        "state_id": "a1",
                        "turn_key": "MAP:1",
                        "status": "awaiting_approval",
                        "final_decision": "choose 0",
                    }
                ),
                encoding="utf-8",
            )
            (d / "0002.ai.json").write_text(
                json.dumps(
                    {
                        "state_id": "a2",
                        "turn_key": "COMBAT:2",
                        "status": "executed",
                        "reasoning_profile_name": "legacy_binary",
                        "reasoning_effort_used": "medium",
                    }
                ),
                encoding="utf-8",
            )
            (d / "run_end_snapshot.json").write_text(
                json.dumps(
                    {
                        "derived": {
                            "victory": True,
                            "floor": 51,
                            "class": "Ironclad",
                        }
                    }
                ),
                encoding="utf-8",
            )
            (d / "run_metrics.ndjson").write_text(
                '{"type":"run_end","derived":{"victory":false}}\n',
                encoding="utf-8",
            )

            report = RunAnalyzer.analyze(d)
            self.assertEqual(report.decision_count, 2)
            self.assertEqual(report.decisions[0].state_id, "a1")
            self.assertTrue(report.run_end_derived.get("victory"))
            self.assertEqual(report.run_metrics_line_count, 1)


if __name__ == "__main__":
    unittest.main()
