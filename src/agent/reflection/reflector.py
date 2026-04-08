"""LLM-powered lesson extraction from a RunReport."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.agent.config import AgentConfig
from src.agent.reflection.report_types import RunReport
from src.agent.reflection.schemas import EpisodicDraft, ProceduralLessonDraft

log = logging.getLogger(__name__)

_REFLECTOR_SYSTEM = """You are a post-run analyst for a Slay the Spire AI agent.

You receive a JSON RunReport (truncated if very long) and a short list of existing procedural lesson snippets to avoid duplicates.

Respond with a single JSON object only (no markdown fences), shape:
{
  "procedural_lessons": [
    {
      "lesson": "One concrete, actionable sentence.",
      "context_tags": { "act": "1", "screen": "combat", "character": "ironclad" },
      "confidence": 0.65
    }
  ],
  "episodic": {
    "character": "",
    "outcome": "victory|defeat|incomplete",
    "floor_reached": 0,
    "cause_of_death": "",
    "deck_archetype": "",
    "key_decisions": ["short bullet", "..."],
    "run_summary": "2-4 sentences",
    "context_tags": {}
  }
}

Rules:
- procedural_lessons: 3-10 items unless the run_report.decision_count is below 10, then at most 2 items.
- Each confidence must be between 0.4 and 0.8 inclusive.
- Lessons must be new compared to the existing_snippets list (rephrase if needed).
- episodic is required; use outcome "incomplete" if the run ended abruptly or data is missing.
"""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(raw[start : i + 1])
                    return data if isinstance(data, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _clamp_lesson_confidence(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.6
    return max(0.4, min(0.8, v))


def reflect_on_run(
    run_report: RunReport,
    existing_lessons: list[str],
    llm_client: Any,
    config: AgentConfig,
) -> tuple[list[ProceduralLessonDraft], EpisodicDraft | None]:
    """Return procedural drafts and optional episodic draft; empty on failure."""
    try:
        report_json = run_report.model_dump_json()
        if len(report_json) > 28000:
            report_json = report_json[:28000] + "\n…(truncated)…"

        snippets = "\n".join(f"- {s[:120]}" for s in existing_lessons[:80])
        user = (
            f"run_report_json:\n{report_json}\n\n"
            f"existing_lesson_snippets (dedup hints):\n{snippets or '(none)'}\n"
        )

        out = llm_client.generate_plain_completion(
            system_prompt=_REFLECTOR_SYSTEM,
            user_content=user,
            model_key="reasoning",
            max_output_tokens=4096,
            reasoning_effort="high",
        )
        text = str(out.get("raw_output") or "")
        data = _extract_json_object(text)
        if not data:
            log.warning("reflector: could not parse JSON from model output")
            return [], None

        max_lessons = 2 if run_report.decision_count < 10 else 10
        raw_pl = data.get("procedural_lessons")
        procedural: list[ProceduralLessonDraft] = []
        if isinstance(raw_pl, list):
            for item in raw_pl:
                if not isinstance(item, dict):
                    continue
                lesson = str(item.get("lesson") or "").strip()
                if not lesson:
                    continue
                tags = item.get("context_tags")
                if not isinstance(tags, dict):
                    tags = {}
                procedural.append(
                    ProceduralLessonDraft(
                        lesson=lesson,
                        context_tags=tags,
                        confidence=_clamp_lesson_confidence(item.get("confidence")),
                    )
                )
                if len(procedural) >= max_lessons:
                    break

        episodic: EpisodicDraft | None = None
        ep = data.get("episodic")
        if isinstance(ep, dict):
            kd = ep.get("key_decisions")
            if not isinstance(kd, list):
                kd = []
            ct = ep.get("context_tags")
            if not isinstance(ct, dict):
                ct = {}
            fr = ep.get("floor_reached", 0)
            try:
                fr_int = int(fr) if fr is not None and str(fr).strip() != "" else 0
            except (TypeError, ValueError):
                fr_int = 0
            episodic = EpisodicDraft(
                character=str(ep.get("character") or ""),
                outcome=str(ep.get("outcome") or ""),
                floor_reached=fr_int,
                cause_of_death=str(ep.get("cause_of_death") or ""),
                deck_archetype=str(ep.get("deck_archetype") or ""),
                key_decisions=[str(x) for x in kd if str(x).strip()],
                run_summary=str(ep.get("run_summary") or ""),
                context_tags=ct,
            )

        cap = max(1, int(config.reflection_max_lessons_per_run))
        procedural = procedural[:cap]

        return procedural, episodic
    except Exception as exc:  # noqa: BLE001
        log.warning("reflector failed: %s", exc)
        return [], None

