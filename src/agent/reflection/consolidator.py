"""Deterministic procedural memory maintenance (archive low-confidence rows)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agent.config import AgentConfig
from src.agent.memory import MemoryStore
from src.agent.memory.types import ProceduralEntry
from src.agent.tracing import utc_now_iso


@dataclass
class ConsolidationSummary:
    archived_ids: list[str] = field(default_factory=list)
    log_path: str = ""


def _append_consolidation_log(memory_dir: Path, record: dict[str, Any]) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / "consolidation_log.ndjson"
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def consolidate_procedural_memory(store: MemoryStore, config: AgentConfig) -> ConsolidationSummary:
    """Set ``status=archived`` for active procedural rows with confidence below threshold.

    Merge / promote / weaken with LLM or cross-run validation is deferred.
    """
    summary = ConsolidationSummary()
    summary.log_path = str((store.memory_dir / "consolidation_log.ndjson").resolve())
    threshold = float(config.consolidation_confidence_archive_threshold)
    out: list[ProceduralEntry] = []
    for entry in store.procedural_entries:
        e = entry.model_copy(deep=True)
        status = (e.status or "").lower()
        if status == "archived":
            out.append(e)
            continue
        if float(e.confidence) < threshold:
            e.status = "archived"
            summary.archived_ids.append(e.id)
        out.append(e)

    store.rewrite_procedural(out)
    _append_consolidation_log(
        store.memory_dir,
        {
            "timestamp": utc_now_iso(),
            "action": "consolidation_pass",
            "archived_ids": summary.archived_ids,
            "threshold": threshold,
        },
    )
    return summary
