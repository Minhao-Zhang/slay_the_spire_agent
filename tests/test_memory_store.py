from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.agent.memory import MemoryStore, build_context_tags
from src.agent.memory.types import ContextTags, ProceduralEntry


class TestMemoryStore(unittest.TestCase):
    def test_expert_guides_load_and_retrieve_as_expert_layer(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            strat = base / "strategy"
            expert = base / "expert"
            mem = base / "memory"
            strat.mkdir()
            expert.mkdir()
            mem.mkdir()
            (strat / "gen.md").write_text(
                "---\ntags: [general]\n---\nGeneral strategy.",
                encoding="utf-8",
            )
            (expert / "deep.md").write_text(
                "---\ntags: [act1, combat, general]\n---\nExpert act1 combat note.",
                encoding="utf-8",
            )
            store = MemoryStore(memory_dir=mem, strategy_dir=strat, expert_guides_dir=expert)
            idx = store.knowledge_index_entries()
            ids = {e["id"] for e in idx}
            self.assertIn("strategy:gen.md", ids)
            self.assertIn("expert:deep.md", ids)
            ctx = ContextTags(
                act="act1",
                floor=5,
                screen_type="COMBAT",
                character="IRONCLAD",
                ascension=0,
                enemy_slugs=(),
                event_slug="",
                relic_slugs=(),
                flat_tags=frozenset({"act1", "combat", "general", "ironclad"}),
            )
            hits = store.retrieve(
                ctx, max_results=10, char_budget=5000, min_procedural_confidence=0.5
            )
            layers = [h.layer for h in hits]
            self.assertIn("expert", layers)
            expert_hit = next(h for h in hits if h.layer == "expert")
            self.assertIn("Expert act1", expert_hit.body)

    def test_retrieve_layer_order_and_skips_archived(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            strat = base / "strategy"
            mem = base / "memory"
            strat.mkdir()
            mem.mkdir()
            (strat / "only_shop.md").write_text(
                "---\ntags: [shop, general]\n---\nShop only body.",
                encoding="utf-8",
            )
            proc_path = mem / "procedural.ndjson"
            proc_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": "p_arch",
                                "created_at": "t",
                                "lesson": "archived lesson",
                                "context_tags": {"screen": "combat"},
                                "confidence": 1.0,
                                "status": "archived",
                            }
                        ),
                        json.dumps(
                            {
                                "id": "p_live",
                                "created_at": "t",
                                "lesson": "live combat lesson",
                                "context_tags": {"screen": "combat"},
                                "confidence": 1.0,
                                "status": "active",
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (mem / "episodic.ndjson").write_text(
                json.dumps(
                    {
                        "id": "e1",
                        "character": "ironclad",
                        "outcome": "victory",
                        "run_summary": "episodic summary",
                        "context_tags": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            store = MemoryStore(memory_dir=mem, strategy_dir=strat)
            ctx = ContextTags(
                act="act1",
                floor=5,
                screen_type="COMBAT",
                character="IRONCLAD",
                ascension=0,
                enemy_slugs=(),
                event_slug="",
                relic_slugs=(),
                flat_tags=frozenset({"combat", "general", "ironclad", "screen_combat"}),
            )
            hits = store.retrieve(
                ctx,
                max_results=10,
                char_budget=10_000,
                min_procedural_confidence=0.0,
            )
            layers = [h.layer for h in hits]
            self.assertEqual(layers[0], "procedural")
            self.assertIn("strategy", layers)
            self.assertIn("episodic", layers)
            bodies = " ".join(h.body for h in hits)
            self.assertIn("live combat lesson", bodies)
            self.assertNotIn("archived lesson", bodies)

    def test_min_procedural_confidence(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            strat = base / "strategy"
            mem = base / "memory"
            strat.mkdir()
            mem.mkdir()
            (strat / "empty.md").write_text("---\ntags: [x]\n---\nnope", encoding="utf-8")
            (mem / "procedural.ndjson").write_text(
                json.dumps(
                    {
                        "id": "low",
                        "created_at": "t",
                        "lesson": "low conf",
                        "context_tags": {"k": "combat"},
                        "confidence": 0.1,
                        "status": "active",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            store = MemoryStore(memory_dir=mem, strategy_dir=strat)
            ctx = ContextTags(
                act=None,
                floor=None,
                screen_type="COMBAT",
                character="",
                ascension=None,
                enemy_slugs=(),
                event_slug="",
                relic_slugs=(),
                flat_tags=frozenset({"combat", "general", "reference"}),
            )
            hits = store.retrieve(
                ctx,
                max_results=5,
                char_budget=5000,
                min_procedural_confidence=0.5,
            )
            self.assertTrue(all(h.layer != "procedural" for h in hits))

    def test_char_budget_truncates_or_caps(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            strat = base / "strategy"
            mem = base / "memory"
            strat.mkdir()
            mem.mkdir()
            (strat / "big.md").write_text(
                "---\ntags: [general]\n---\n" + ("word " * 2000),
                encoding="utf-8",
            )
            store = MemoryStore(memory_dir=mem, strategy_dir=strat)
            ctx = ContextTags(
                act=None,
                floor=None,
                screen_type="NONE",
                character="",
                ascension=None,
                enemy_slugs=(),
                event_slug="",
                relic_slugs=(),
                flat_tags=frozenset({"general", "reference"}),
            )
            hits = store.retrieve(
                ctx,
                max_results=3,
                char_budget=80,
                min_procedural_confidence=0.0,
            )
            self.assertTrue(hits)
            total = sum(len(h.body) for h in hits)
            self.assertLessEqual(total, 80)

    def test_append_procedural_updates_memory(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            strat = base / "strategy"
            mem = base / "memory"
            strat.mkdir()
            mem.mkdir()
            (strat / "t.md").write_text("---\ntags: [z]\n---\nx", encoding="utf-8")
            store = MemoryStore(memory_dir=mem, strategy_dir=strat)
            entry = ProceduralEntry(
                id="new1",
                created_at="now",
                lesson="appended",
                context_tags={"z": "z"},
                confidence=1.0,
            )
            store.append_procedural(entry)
            store.reload()
            ctx = ContextTags(
                act=None,
                floor=None,
                screen_type="NONE",
                character="",
                ascension=None,
                enemy_slugs=(),
                event_slug="",
                relic_slugs=(),
                flat_tags=frozenset({"z"}),
            )
            hits = store.retrieve(
                ctx, max_results=5, char_budget=500, min_procedural_confidence=0.0
            )
            self.assertTrue(any(h.body == "appended" for h in hits))


class TestContextTags(unittest.TestCase):
    def test_build_context_tags_smoke(self) -> None:
        vm = {
            "header": {
                "class": "Ironclad",
                "floor": 12,
                "act": 2,
                "ascension_level": 5,
            },
            "screen": {"type": "COMBAT"},
            "combat": {
                "monsters": [{"name": "Lagavulin", "is_gone": False}],
                "player_block": 0,
            },
            "inventory": {"relics": [{"name": "Burning Blood"}]},
            "map": {"boss_name": "Automaton"},
        }
        tags = build_context_tags(vm)
        self.assertEqual(tags.screen_type, "COMBAT")
        self.assertIn("ironclad", tags.flat_tags)
        self.assertIn("lagavulin", tags.flat_tags)
        self.assertIn("combat", tags.flat_tags)
        self.assertIn("general", tags.flat_tags)


if __name__ == "__main__":
    unittest.main()
