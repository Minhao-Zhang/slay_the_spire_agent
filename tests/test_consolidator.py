from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.agent.config import AgentConfig
from src.agent.memory import MemoryStore
from src.agent.memory.types import ProceduralEntry
from src.agent.reflection.consolidator import consolidate_procedural_memory


class TestConsolidator(unittest.TestCase):
    def test_archives_below_threshold(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            mem = base / "memory"
            strat = base / "strategy"
            mem.mkdir()
            strat.mkdir()
            (strat / "x.md").write_text("---\ntags: [t]\n---\n.", encoding="utf-8")
            proc = mem / "procedural.ndjson"
            proc.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "low",
                                "created_at": "t",
                                "lesson": "weak",
                                "confidence": 0.1,
                                "status": "active",
                            }
                        ),
                        json.dumps(
                            {
                                "id": "ok",
                                "created_at": "t",
                                "lesson": "fine",
                                "confidence": 0.8,
                                "status": "active",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            store = MemoryStore(memory_dir=mem, strategy_dir=strat)
            cfg = AgentConfig().model_copy(update={"consolidation_confidence_archive_threshold": 0.2})
            summary = consolidate_procedural_memory(store, cfg)
            self.assertIn("low", summary.archived_ids)
            self.assertNotIn("ok", summary.archived_ids)
            store.reload()
            statuses = {e.id: e.status for e in store.procedural_entries}
            self.assertEqual(statuses["low"], "archived")
            self.assertEqual(statuses["ok"], "active")
            log = (mem / "consolidation_log.ndjson").read_text(encoding="utf-8").strip()
            self.assertIn("consolidation_pass", log)


if __name__ == "__main__":
    unittest.main()
