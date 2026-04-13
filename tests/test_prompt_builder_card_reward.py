from __future__ import annotations

import unittest

from src.agent.prompt_builder import _deck_assessment_lines, _screen_content_lines, build_user_prompt


class TestPromptBuilderCardReward(unittest.TestCase):
    def _card_reward_vm(self, deck: list[dict]) -> dict:
        return {
            "combat": None,
            "screen": {
                "type": "CARD_REWARD",
                "content": {"cards": [{"name": "Zap", "kb": {}}]},
            },
            "inventory": {"deck": deck, "relics": [], "potions": []},
            "header": {
                "class": "Ironclad",
                "floor": 5,
                "hp_display": "50/50",
                "gold": 99,
                "energy": "-",
                "turn": "-",
            },
            "actions": [{"label": "Skip", "command": "SKIP"}],
        }

    def test_card_reward_scene_body_has_no_duplicate_deck_block(self) -> None:
        deck = [{"type": "ATTACK", "name": "Strike", "cost": 1}]
        vm = self._card_reward_vm(deck)
        lines = _screen_content_lines(vm)
        text = "\n".join(lines)
        self.assertNotIn("DECK (", text)
        self.assertNotIn("YOUR DECK:", text)
        self.assertIn("Choose one card to add to your deck", text)

    def test_card_reward_prompt_includes_deck_assessment(self) -> None:
        deck = []
        for i in range(26):
            deck.append(
                {
                    "type": "ATTACK" if i % 2 == 0 else "SKILL",
                    "name": f"C{i}",
                    "cost": 1,
                    "upgrades": 1 if i == 0 else 0,
                }
            )
        vm = self._card_reward_vm(deck)
        text = build_user_prompt(vm, "s1", [])
        self.assertIn("### Deck assessment", text)
        self.assertIn("DECK (26 cards", text)
        self.assertIn("ATTACK=13", text)
        self.assertIn("SKILL=13", text)
        self.assertIn("1 upgraded)", text)
        self.assertIn("WARNING: Deck has 26 cards", text)
        self.assertIn("Larger decks lose consistency", text)

    def test_deck_assessment_lines_cost_curve_and_types(self) -> None:
        deck = [
            {"type": "ATTACK", "name": "A", "cost": 1},
            {"type": "SKILL", "name": "B", "cost": 2, "upgrades": 1},
        ]
        lines = _deck_assessment_lines({"inventory": {"deck": deck}})
        joined = "\n".join(lines)
        self.assertIn("DECK (2 cards, 1 upgraded)", joined)
        self.assertIn("Cost curve:", joined)
        self.assertIn("1-cost=", joined)
        self.assertIn("2-cost=", joined)
        self.assertIn("ATTACK: A", joined)
        self.assertIn("SKILL: B+", joined)


if __name__ == "__main__":
    unittest.main()
