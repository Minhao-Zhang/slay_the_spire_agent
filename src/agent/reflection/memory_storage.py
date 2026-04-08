"""Append reflection output to procedural / episodic NDJSON via MemoryStore.

Assumes a single writer process appends to ``data/memory/*.ndjson`` (game bridge).
No file locking; concurrent writers could interleave lines.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from src.agent.config import get_agent_config
from src.agent.memory import MemoryStore
from src.agent.memory.tag_utils import flatten_tag_mapping, slugify_token
from src.agent.memory.types import EpisodicEntry, ProceduralEntry
from src.agent.tracing import utc_now_iso

from .schemas import ReflectionPersistInput, ReflectionPersistResult


def normalize_reflection_context_tags(raw: dict[str, Any]) -> dict[str, Any]:
    """Slugify string keys and string/list values for consistent retrieval overlap."""
    out: dict[str, Any] = {}
    for k, v in (raw or {}).items():
        sk = slugify_token(str(k)) or str(k).strip().lower().replace(" ", "_")
        if not sk:
            continue
        if isinstance(v, str):
            sv = slugify_token(v)
            if sv:
                out[sk] = sv
        elif isinstance(v, (list, tuple)):
            slist = [slugify_token(str(x)) for x in v]
            slist = [x for x in slist if x]
            out[sk] = slist
        else:
            out[sk] = v
    return out


def _clamp_confidence(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = len(a | b)
    return float(len(a & b)) / float(union) if union else 0.0


def _word_jaccard(a: str, b: str) -> float:
    def words(s: str) -> set[str]:
        return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}

    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    union = len(wa | wb)
    return float(inter) / float(union) if union else 0.0


def _find_duplicate_lesson_index(
    rows: list[ProceduralEntry],
    lesson: str,
    norm_tags: dict[str, Any],
) -> int | None:
    flat_d = flatten_tag_mapping(norm_tags)
    for i, e in enumerate(rows):
        if (e.status or "").lower() == "archived":
            continue
        flat_e = flatten_tag_mapping(e.context_tags)
        if _jaccard(flat_d, flat_e) > 0.8 and _word_jaccard(lesson, e.lesson) > 0.7:
            return i
    return None


def persist_reflection_to_memory(
    store: MemoryStore,
    data: ReflectionPersistInput,
    *,
    max_procedural_lessons: int | None = None,
) -> ReflectionPersistResult:
    """Persist reflector output: all procedural rows first, then optional episodic row."""
    if max_procedural_lessons is None:
        max_procedural_lessons = get_agent_config().reflection_max_lessons_per_run

    created_at = utc_now_iso()
    result = ReflectionPersistResult()
    cap = max(0, int(max_procedural_lessons))
    appended = 0

    procedural_rows: list[ProceduralEntry] = list(store.procedural_entries)
    dirty_procedural = False

    for draft in data.procedural_lessons:
        text = (draft.lesson or "").strip()
        if not text:
            result.procedural_skipped_empty += 1
            continue

        norm_tags = normalize_reflection_context_tags(draft.context_tags)
        dup_i = _find_duplicate_lesson_index(procedural_rows, text, norm_tags)
        if dup_i is not None:
            old = procedural_rows[dup_i]
            procedural_rows[dup_i] = old.model_copy(
                update={"times_validated": int(old.times_validated) + 1}
            )
            result.procedural_merged += 1
            dirty_procedural = True
            continue

        if appended >= cap:
            result.procedural_skipped_cap += 1
            continue

        pid = str(uuid.uuid4())
        status = (draft.status or "").strip().lower() or "active"
        entry = ProceduralEntry(
            id=pid,
            created_at=created_at,
            source_run=data.run_id.strip(),
            lesson=text,
            context_tags=norm_tags,
            confidence=_clamp_confidence(draft.confidence),
            times_validated=0,
            times_contradicted=0,
            status=status,
        )
        procedural_rows.append(entry)
        result.procedural_ids.append(pid)
        result.procedural_appended += 1
        appended += 1
        dirty_procedural = True

    if dirty_procedural:
        store.rewrite_procedural(procedural_rows)

    if data.episodic is not None:
        ep = data.episodic
        eid = str(uuid.uuid4())
        entry = EpisodicEntry(
            id=eid,
            run_dir=data.run_dir.strip(),
            timestamp=created_at,
            character=(ep.character or "").strip(),
            outcome=(ep.outcome or "").strip(),
            floor_reached=ep.floor_reached,
            cause_of_death=(ep.cause_of_death or "").strip(),
            deck_archetype=(ep.deck_archetype or "").strip(),
            key_decisions=list(ep.key_decisions),
            run_summary=(ep.run_summary or "").strip(),
            context_tags=normalize_reflection_context_tags(ep.context_tags),
        )
        store.append_episodic(entry)
        result.episodic_appended = 1
        result.episodic_id = eid

    return result
