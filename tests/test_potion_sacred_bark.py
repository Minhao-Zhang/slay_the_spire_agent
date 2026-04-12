"""Potion KB enrichment respects Sacred Bark (doubled parenthesized values)."""

import unittest

from src.ui import state_processor


class TestPotionSacredBark(unittest.TestCase):
    def test_enrich_without_sacred_bark_uses_base_numbers(self) -> None:
        row = _enrich_potion_row("Strength Potion", False)
        eff = (row.get("kb") or {}).get("effect", "")
        self.assertRegex(eff, r"Gain 2 \[Strength\]")
        self.assertNotIn("(4)", eff)

    def test_enrich_with_sacred_bark_uses_doubled_values(self) -> None:
        row = _enrich_potion_row("Strength Potion", True)
        eff = (row.get("kb") or {}).get("effect", "")
        self.assertRegex(eff, r"Gain 4 \[Strength\]")
        self.assertNotIn("(4)", eff)

    def test_player_has_sacred_bark_detects_relic(self) -> None:
        game = {"relics": [{"name": "Sacred Bark"}, {"name": "Vajra"}]}
        self.assertTrue(state_processor._player_has_sacred_bark(game))
        self.assertFalse(state_processor._player_has_sacred_bark({"relics": []}))


def _enrich_potion_row(name: str, has_sb: bool) -> dict:
    return state_processor._enrich_potion({"name": name}, has_sacred_bark=has_sb)


if __name__ == "__main__":
    unittest.main()
