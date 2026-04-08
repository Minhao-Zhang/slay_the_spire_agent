"""Orchestrate the full post-game reflection pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.agent.config import AgentConfig
from src.agent.memory import MemoryStore
from src.agent.reflection.analyzer import RunAnalyzer
from src.agent.reflection.memory_storage import persist_reflection_to_memory
from src.agent.reflection.reflector import reflect_on_run
from src.agent.reflection.schemas import EpisodicDraft, ReflectionPersistInput, ReflectionPersistResult

log = logging.getLogger(__name__)


def pending_reflection_dirs(games_root: Path, *, limit: int = 10) -> list[Path]:
    """Directories with ``run_report.json`` but no ``reflection_output.json``."""
    if not games_root.is_dir():
        return []
    candidates: list[Path] = []
    for p in sorted(games_root.iterdir(), key=lambda x: x.name, reverse=True):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if (p / "run_report.json").is_file() and not (p / "reflection_output.json").is_file():
            candidates.append(p)
        if len(candidates) >= limit:
            break
    return candidates


def _default_episodic_from_report(report: RunReport) -> EpisodicDraft:
    outcome = "incomplete"
    if report.victory is True:
        outcome = "victory"
    elif report.victory is False:
        outcome = "defeat"
    cod = report.cause_of_death or ""
    if cod == "no_run_end_snapshot":
        outcome = "incomplete"
    keys = [str(x) for x in (report.path_summary[:5] if report.path_summary else [])]
    summary_parts = [
        f"Character {report.character or 'unknown'}",
        f"floor {report.floor_reached}",
        f"outcome {outcome}",
    ]
    return EpisodicDraft(
        character=report.character,
        outcome=outcome,
        floor_reached=report.floor_reached,
        cause_of_death=cod,
        deck_archetype="",
        key_decisions=keys,
        run_summary=". ".join(summary_parts) + ".",
        context_tags={"act": str(report.run_end_derived.get("act") or "")} if report.run_end_derived else {},
    )


def run_reflection_pipeline(
    game_dir: Path,
    memory_store: MemoryStore,
    llm_client: Any,
    config: AgentConfig,
) -> ReflectionPersistResult | None:
    game_dir = game_dir.resolve()
    report_path = game_dir / "run_report.json"
    output_path = game_dir / "reflection_output.json"

    result: ReflectionPersistResult | None = None
    error: str | None = None

    try:
        report = RunAnalyzer.analyze(game_dir)
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        existing = [e.lesson[:80] for e in memory_store.procedural_entries]
        lessons, episodic = reflect_on_run(report, existing, llm_client, config)

        if episodic is None:
            episodic = _default_episodic_from_report(report)

        inp = ReflectionPersistInput(
            run_dir=str(game_dir),
            run_id=game_dir.name,
            procedural_lessons=lessons,
            episodic=episodic,
        )
        result = persist_reflection_to_memory(memory_store, inp)
    except Exception as exc:  # noqa: BLE001
        error = repr(exc)
        log.exception("run_reflection_pipeline failed for %s", game_dir)

    payload: dict[str, Any] = {
        "ok": error is None,
        "run_dir": str(game_dir),
        "error": error,
        "persist": result.model_dump(mode="json") if result else None,
    }
    try:
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("could not write reflection_output.json: %s", exc)

    return result
