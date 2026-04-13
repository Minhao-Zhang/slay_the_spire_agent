from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agent.schemas import AgentTrace, TraceTokenUsage
from src.agent.tracing import (
    append_ai_decision_run_metric,
    build_persisted_ai_log,
    derive_card_reward_action,
    derive_potion_used,
)


class TestBuildPersistedAiLog(unittest.TestCase):
    def test_deck_size_and_retrieved_lesson_ids_round_trip(self) -> None:
        trace = AgentTrace(
            decision_id="d1",
            state_id="s1",
            turn_key="MAP:1",
            timestamp="2020-01-01T00:00:00+00:00",
            status="executed",
            agent_mode="propose",
            deck_size=17,
            retrieved_lesson_ids=["strategy:foo.md", "procedural:p1"],
            experiment_tag="exp-a",
            experiment_id="abc123deadbeef",
            strategist_ran=True,
        )
        log = build_persisted_ai_log(trace)
        self.assertEqual(log.deck_size, 17)
        self.assertEqual(log.retrieved_lesson_ids, ["strategy:foo.md", "procedural:p1"])
        self.assertEqual(log.experiment_tag, "exp-a")
        self.assertEqual(log.experiment_id, "abc123deadbeef")
        self.assertTrue(log.strategist_ran)


class TestDeriveSurrogateMetrics(unittest.TestCase):
    def _trace(
        self,
        *,
        screen: str = "COMBAT",
        final: str | None = None,
        sequence: list[str] | None = None,
        deck: int | None = 12,
    ) -> AgentTrace:
        return AgentTrace(
            decision_id="d1",
            state_id="s1",
            turn_key="t1",
            timestamp="2020-01-01T00:00:00+00:00",
            status="executed",
            agent_mode="propose",
            screen_type=screen,
            final_decision=final,
            final_decision_sequence=sequence or [],
            deck_size=deck,
        )

    def test_card_reward_skip_and_take(self) -> None:
        self.assertIsNone(derive_card_reward_action(self._trace(screen="MAP")))
        self.assertEqual(
            derive_card_reward_action(self._trace(screen="CARD_REWARD", final="SKIP")),
            "skip",
        )
        self.assertEqual(
            derive_card_reward_action(self._trace(screen="CARD_REWARD", final="choose 0")),
            "take",
        )
        self.assertEqual(
            derive_card_reward_action(
                self._trace(screen="CARD_REWARD", sequence=["choose 2"])
            ),
            "take",
        )

    def test_potion_used(self) -> None:
        self.assertFalse(derive_potion_used(self._trace(final="END")))
        self.assertTrue(derive_potion_used(self._trace(final="POTION USE 0")))
        self.assertTrue(
            derive_potion_used(self._trace(sequence=["POTION USE 1 0"]))
        )


class TestAppendAiDecisionRunMetric(unittest.TestCase):
    def test_ndjson_includes_phase4_fields(self) -> None:
        trace = AgentTrace(
            decision_id="d1",
            state_id="s1",
            turn_key="CARD_REWARD:3",
            timestamp="2020-01-01T00:00:00+00:00",
            status="executed",
            agent_mode="propose",
            screen_type="CARD_REWARD",
            final_decision="SKIP",
            deck_size=20,
            experiment_tag="tag-a",
            experiment_id="deadbeef0001",
            strategist_ran=True,
            token_usage=TraceTokenUsage(
                input_tokens=100,
                output_tokens=50,
            ),
            latency_ms=999,
            llm_model_used="gpt-test",
        )
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            state_path = run_dir / "42.json"
            state_path.write_text("{}", encoding="utf-8")
            append_ai_decision_run_metric(run_dir, trace, state_path)
            lines = (run_dir / "run_metrics.ndjson").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["type"], "ai_decision")
        self.assertEqual(row["experiment_tag"], "tag-a")
        self.assertEqual(row["experiment_id"], "deadbeef0001")
        self.assertEqual(row["screen_type"], "CARD_REWARD")
        self.assertEqual(row["deck_size"], 20)
        self.assertEqual(row["card_reward_action"], "skip")
        self.assertFalse(row["potion_used"])
        self.assertEqual(row["event_index"], 42)


if __name__ == "__main__":
    unittest.main()
