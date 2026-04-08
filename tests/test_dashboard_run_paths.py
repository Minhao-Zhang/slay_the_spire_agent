"""Regression: run directory resolution for metrics / frames API."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestSafeRunDir(unittest.TestCase):
    def test_resolves_under_logs_or_logs_games(self) -> None:
        from src.ui import dashboard

        with tempfile.TemporaryDirectory() as td:
            games = Path(td) / "logs" / "games"
            legacy = Path(td) / "logs"
            games.mkdir(parents=True)
            (games / "run_a").mkdir()
            (legacy / "run_b").mkdir()

            with patch.object(dashboard, "LOG_GAMES_DIR", str(games)), patch.object(
                dashboard, "LOGS_DIR", str(legacy)
            ):
                self.assertEqual(
                    dashboard._safe_run_dir("run_a"),
                    str(games / "run_a"),
                )
                self.assertEqual(
                    dashboard._safe_run_dir("run_b"),
                    str(legacy / "run_b"),
                )

    def test_rejects_path_traversal(self) -> None:
        from src.ui import dashboard

        self.assertIsNone(dashboard._safe_run_dir("../x"))
        self.assertIsNone(dashboard._safe_run_dir("a/b"))


if __name__ == "__main__":
    unittest.main()
