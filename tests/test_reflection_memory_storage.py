from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agent.memory import MemoryStore
from src.agent.memory.types import EpisodicEntry, ProceduralEntry
from src.agent.reflection import (
    EpisodicDraft,
    ProceduralLessonDraft,
    ReflectionPersistInput,
    normalize_reflection_context_tags,
    persist_reflection_to_memory,
)


class TestNormalizeReflectionContextTags(unittest.TestCase):
    def test_slugifies_strings_and_lists(self) -> None:
        raw = {"Screen Type": "Combat Elite", "tags": ["Ironclad", "ACT 1"]}
        out = normalize_reflection_context_tags(raw)
        self.assertEqual(out.get("screen_type"), "combat_elite")
        self.assertEqual(out.get("tags"), ["ironclad", "act_1"])


class TestPersistReflectionToMemory(unittest.TestCase):
    def _store(self) -> tuple[MemoryStore, Path, Path]:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        base = Path(td.name)
        mem = base / "memory"
        kn = base / "knowledge"
        mem.mkdir()
        kn.mkdir()
        (kn / "x.md").write_text("---\ntags: [t]\n---\n.", encoding="utf-8")
        return MemoryStore(memory_dir=mem, knowledge_dir=kn), mem, kn

    def test_appends_procedural_and_episodic(self) -> None:
        store, mem, _ = self._store()
        data = ReflectionPersistInput(
            run_dir=str(mem.parent / "run_xyz"),
            run_id="run_xyz",
            procedural_lessons=[
                ProceduralLessonDraft(
                    lesson="Block before big hits.",
                    context_tags={"screen": "combat", "act": 1},
                    confidence=0.7,
                ),
                ProceduralLessonDraft(lesson="Second tip.", context_tags={"floor": 5}),
            ],
            episodic=EpisodicDraft(
                character="Ironclad",
                outcome="defeat",
                floor_reached=12,
                run_summary="Lost to Time Eater.",
                key_decisions=["Took risky path"],
            ),
        )
        result = persist_reflection_to_memory(store, data, max_procedural_lessons=10)
        self.assertEqual(result.procedural_appended, 2)
        self.assertEqual(result.episodic_appended, 1)
        self.assertEqual(len(result.procedural_ids), 2)
        self.assertIsNotNone(result.episodic_id)

        proc_lines = (mem / "procedural.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(proc_lines), 2)
        p0 = ProceduralEntry.model_validate(json.loads(proc_lines[0]))
        self.assertEqual(p0.source_run, "run_xyz")
        self.assertEqual(p0.lesson, "Block before big hits.")
        self.assertEqual(p0.status, "active")
        self.assertGreaterEqual(p0.confidence, 0.69)

        epi_lines = (mem / "episodic.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(epi_lines), 1)
        e0 = EpisodicEntry.model_validate(json.loads(epi_lines[0]))
        self.assertEqual(e0.character, "Ironclad")
        self.assertEqual(e0.outcome, "defeat")
        self.assertEqual(e0.run_summary, "Lost to Time Eater.")

    def test_skips_empty_lessons(self) -> None:
        store, mem, _ = self._store()
        data = ReflectionPersistInput(
            run_dir="r",
            run_id="r1",
            procedural_lessons=[
                ProceduralLessonDraft(lesson="   ", context_tags={}),
                ProceduralLessonDraft(lesson="Valid.", context_tags={}),
            ],
        )
        result = persist_reflection_to_memory(store, data, max_procedural_lessons=10)
        self.assertEqual(result.procedural_skipped_empty, 1)
        self.assertEqual(result.procedural_appended, 1)
        proc_lines = (mem / "procedural.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(proc_lines), 1)

    def test_clamps_confidence(self) -> None:
        store, mem, _ = self._store()
        data = ReflectionPersistInput(
            run_dir="r",
            run_id="r1",
            procedural_lessons=[
                ProceduralLessonDraft(lesson="Hi", confidence=99.0),
                ProceduralLessonDraft(lesson="Lo", confidence=-1.0),
            ],
        )
        persist_reflection_to_memory(store, data, max_procedural_lessons=10)
        lines = (mem / "procedural.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(json.loads(lines[0])["confidence"], 1.0)
        self.assertEqual(json.loads(lines[1])["confidence"], 0.0)

    def test_respects_max_procedural_cap(self) -> None:
        store, mem, _ = self._store()
        data = ReflectionPersistInput(
            run_dir="r",
            run_id="r1",
            procedural_lessons=[
                ProceduralLessonDraft(lesson=f"L{i}", context_tags={}) for i in range(5)
            ],
        )
        result = persist_reflection_to_memory(store, data, max_procedural_lessons=2)
        self.assertEqual(result.procedural_appended, 2)
        self.assertEqual(result.procedural_skipped_cap, 3)
        lines = (mem / "procedural.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)

    def test_custom_status_on_draft(self) -> None:
        store, mem, _ = self._store()
        data = ReflectionPersistInput(
            run_dir="r",
            run_id="r1",
            procedural_lessons=[
                ProceduralLessonDraft(lesson="Archived lesson", status="archived"),
            ],
        )
        persist_reflection_to_memory(store, data, max_procedural_lessons=10)
        line = (mem / "procedural.ndjson").read_text(encoding="utf-8").strip()
        self.assertEqual(json.loads(line)["status"], "archived")

    def test_duplicate_lesson_merges_into_existing(self) -> None:
        store, mem, _ = self._store()
        seed = ProceduralEntry(
            id="existing",
            created_at="t0",
            source_run="old",
            lesson="Block before the enemy telegraphs a large attack on elites.",
            context_tags={"screen": "combat", "act": "2"},
            confidence=0.7,
            times_validated=1,
            status="active",
        )
        store.append_procedural(seed)
        data = ReflectionPersistInput(
            run_dir="r",
            run_id="r2",
            procedural_lessons=[
                ProceduralLessonDraft(
                    lesson="Block before the enemy telegraphs a large attack on elites.",
                    context_tags={"screen": "combat", "act": "2"},
                    confidence=0.55,
                ),
                ProceduralLessonDraft(lesson="Totally new lesson about shops.", context_tags={"screen": "shop"}),
            ],
        )
        result = persist_reflection_to_memory(store, data, max_procedural_lessons=10)
        self.assertEqual(result.procedural_merged, 1)
        self.assertEqual(result.procedural_appended, 1)
        store.reload()
        lessons = {e.lesson: e.times_validated for e in store.procedural_entries}
        self.assertEqual(lessons[seed.lesson], 2)


if __name__ == "__main__":
    unittest.main()
