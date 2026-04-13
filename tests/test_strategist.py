from __future__ import annotations

import unittest

from src.agent.memory.types import RetrievalHit
from src.agent.strategist import map_selected_ids_to_hits, parse_strategist_json


def _hit(layer: str, ref: str, title: str = "t") -> RetrievalHit:
    return RetrievalHit(
        layer=layer,  # type: ignore[arg-type]
        score=1.0,
        title=title,
        body="b",
        source_ref=ref,
    )


class TestStrategistParse(unittest.TestCase):
    def test_parse_json_with_surrounding_text(self) -> None:
        raw = 'noise {"selected_entry_ids": ["strategy:a.md"], "turn_plan": "skip"} tail'
        data = parse_strategist_json(raw)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.get("selected_entry_ids"), ["strategy:a.md"])
        self.assertEqual(data.get("turn_plan"), "skip")

    def test_map_selected_ids(self) -> None:
        pool = [
            _hit("strategy", "/p/strategy/foo.md"),
            _hit("procedural", "id1"),
        ]
        out = map_selected_ids_to_hits(pool, ["strategy:foo.md"], max_hits=8)
        self.assertEqual(len(out), 1)
        self.assertIn("foo", out[0].source_ref)


if __name__ == "__main__":
    unittest.main()
