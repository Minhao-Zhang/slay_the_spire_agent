"""Unit tests for bridge game session helpers (no pytest required: ``python -m unittest``)."""

from __future__ import annotations

import datetime
import unittest

from src.bridge.game_session import (
    build_game_dir_name,
    extract_game_state,
    normalize_seed,
    sanitize_class_slug,
)


class TestGameSession(unittest.TestCase):
    def test_build_game_dir_name_with_seed(self) -> None:
        fixed = datetime.datetime(2025, 4, 7, 14, 32, 5)
        gs = {"seed": "ABCDEFGH1234", "class": "IRONCLAD", "ascension_level": 15}
        name = build_game_dir_name(gs, now=fixed)
        self.assertEqual(name, "2025-04-07-14-32-05_IRONCLAD_A15_ABCDEFGH")

    def test_build_game_dir_name_missing_seed(self) -> None:
        gs = {"class": "IRONCLAD", "ascension_level": 0}
        self.assertIsNone(build_game_dir_name(gs))

    def test_build_game_dir_name_empty_seed(self) -> None:
        self.assertIsNone(build_game_dir_name({"seed": "  ", "class": "X"}))

    def test_sanitize_class_slug(self) -> None:
        self.assertEqual(sanitize_class_slug("defect"), "DEFECT")
        self.assertEqual(sanitize_class_slug("iron clad"), "IRON_CLAD")

    def test_extract_game_state_wrapped(self) -> None:
        raw = {"state": {"game_state": {"seed": "1", "class": "THE_SILENT"}}}
        self.assertEqual(extract_game_state(raw).get("class"), "THE_SILENT")

    def test_normalize_seed(self) -> None:
        self.assertEqual(normalize_seed({"seed": 12345}), "12345")
        self.assertIsNone(normalize_seed({}))


if __name__ == "__main__":
    unittest.main()
