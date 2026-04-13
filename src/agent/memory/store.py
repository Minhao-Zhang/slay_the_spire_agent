from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from src.repo_paths import REPO_ROOT

from .strategy_docs import parse_strategy_markdown
from .tag_utils import flatten_tag_mapping, slugify_token
from .types import ContextTags, EpisodicEntry, ProceduralEntry, RetrievalHit

_E = TypeVar("_E", bound=BaseModel)

log = logging.getLogger(__name__)

KNOWLEDGE_EFFECTIVE_WEIGHT = 1.5
EPISODIC_WEIGHT = 0.85


@dataclass(slots=True)
class _StrategyDoc:
    path: str
    tags: frozenset[str]
    body: str
    layer: str = "strategy"
    effective_weight: float = KNOWLEDGE_EFFECTIVE_WEIGHT


def _procedural_flat(entry: ProceduralEntry) -> frozenset[str]:
    return flatten_tag_mapping(entry.context_tags)


def _episodic_flat(entry: EpisodicEntry) -> frozenset[str]:
    base: set[str] = set()
    for part in (
        entry.character,
        entry.outcome,
        entry.deck_archetype,
        str(entry.floor_reached),
        entry.cause_of_death,
    ):
        t = slugify_token(str(part))
        if t:
            base.add(t)
    base |= set(flatten_tag_mapping(entry.context_tags))
    return frozenset(base)


def _overlap_score(flat_ctx: frozenset[str], flat_entry: frozenset[str]) -> float:
    if not flat_ctx or not flat_entry:
        return 0.0
    return float(len(flat_ctx & flat_entry))


class MemoryStore:
    """L1 knowledge markdown (recursive tree), L2 procedural NDJSON, L3 episodic NDJSON."""

    def __init__(
        self,
        *,
        memory_dir: Path | None = None,
        knowledge_dir: Path | None = None,
    ) -> None:
        self.memory_dir = memory_dir or (REPO_ROOT / "data" / "memory")
        self.knowledge_dir = knowledge_dir or (REPO_ROOT / "data" / "knowledge")
        self._strategy_docs: list[_StrategyDoc] = []
        self._procedural: list[ProceduralEntry] = []
        self._episodic: list[EpisodicEntry] = []
        self.reload()

    def reload(self) -> None:
        self._strategy_docs = self._load_knowledge_tree(self.knowledge_dir)
        self._procedural = self._load_ndjson(
            self.memory_dir / "procedural.ndjson", ProceduralEntry
        )
        self._episodic = self._load_ndjson(self.memory_dir / "episodic.ndjson", EpisodicEntry)

    @property
    def procedural_entries(self) -> list[ProceduralEntry]:
        return list(self._procedural)

    @staticmethod
    def _load_knowledge_tree(base_dir: Path) -> list[_StrategyDoc]:
        out: list[_StrategyDoc] = []
        if not base_dir.is_dir():
            log.debug("knowledge corpus dir missing: %s", base_dir)
            return out
        for path in sorted(base_dir.rglob("*.md")):
            if path.stem.upper() in ("SOURCES", "CHANGELOG", "README"):
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("skip markdown file %s: %s", path, exc)
                continue
            tag_list, body = parse_strategy_markdown(raw)
            tags = frozenset(slugify_token(t) for t in tag_list if slugify_token(t))
            if not body.strip():
                continue
            out.append(
                _StrategyDoc(
                    path=str(path.resolve()),
                    tags=tags,
                    body=body.strip(),
                    layer="strategy",
                    effective_weight=KNOWLEDGE_EFFECTIVE_WEIGHT,
                )
            )
        return out

    @staticmethod
    def _load_ndjson(path: Path, model: type[_E]) -> list[_E]:
        out: list[_E] = []
        if not path.is_file():
            return out
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            log.warning("cannot read %s: %s", path, exc)
            return out
        for i, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                out.append(model.model_validate(data))
            except (json.JSONDecodeError, ValueError) as exc:
                log.debug("skip bad ndjson line %s:%s: %s", path, i, exc)
        return out

    def knowledge_index_entries(self) -> list[dict[str, Any]]:
        """Stable IDs for the retrieval/planning agent (L1 strategy + L2 procedural only)."""
        out: list[dict[str, Any]] = []
        for doc in self._strategy_docs:
            name = Path(doc.path).name
            snip = doc.body.replace("\n", " ").strip()
            if len(snip) > 120:
                snip = snip[:120] + "…"
            lid = "strategy"
            out.append(
                {
                    "id": f"{lid}:{name}",
                    "layer": lid,
                    "tags": sorted(doc.tags),
                    "snippet": snip,
                }
            )
        for e in self._procedural:
            if (e.status or "").lower() == "archived":
                continue
            tags = sorted(_procedural_flat(e))[:32]
            snip = e.lesson.replace("\n", " ").strip()
            if len(snip) > 120:
                snip = snip[:120] + "…"
            out.append(
                {
                    "id": f"procedural:{e.id}",
                    "layer": "procedural",
                    "tags": tags,
                    "snippet": snip,
                }
            )
        return out

    def retrieve(
        self,
        context: ContextTags,
        *,
        max_results: int,
        char_budget: int,
        min_procedural_confidence: float,
    ) -> list[RetrievalHit]:
        flat = context.flat_tags
        procedural_hits: list[RetrievalHit] = []
        for e in self._procedural:
            if (e.status or "").lower() == "archived":
                continue
            if e.confidence < min_procedural_confidence:
                continue
            ov = _overlap_score(flat, _procedural_flat(e))
            if ov <= 0:
                continue
            score = ov * float(e.confidence)
            procedural_hits.append(
                RetrievalHit(
                    layer="procedural",
                    score=score,
                    title=e.id,
                    body=e.lesson.strip(),
                    source_ref=e.id,
                )
            )
        procedural_hits.sort(key=lambda h: h.score, reverse=True)

        strategy_hits: list[RetrievalHit] = []
        for doc in self._strategy_docs:
            if not doc.tags:
                ov = 0.0
            else:
                ov = _overlap_score(flat, doc.tags)
            if ov <= 0:
                continue
            score = ov * doc.effective_weight
            name = Path(doc.path).name
            strategy_hits.append(
                RetrievalHit(
                    layer="strategy",
                    score=score,
                    title=name,
                    body=doc.body,
                    source_ref=doc.path,
                )
            )
        strategy_hits.sort(key=lambda h: h.score, reverse=True)

        episodic_hits: list[RetrievalHit] = []
        for e in self._episodic:
            ov = _overlap_score(flat, _episodic_flat(e))
            if ov <= 0:
                continue
            score = ov * EPISODIC_WEIGHT
            body = e.run_summary.strip() if e.run_summary else ""
            if not body and e.key_decisions:
                if isinstance(e.key_decisions, list):
                    body = "\n".join(f"- {d}" for d in e.key_decisions[:12])
                else:
                    body = str(e.key_decisions)
            episodic_hits.append(
                RetrievalHit(
                    layer="episodic",
                    score=score,
                    title=e.id,
                    body=body or f"Run {e.outcome} as {e.character}",
                    source_ref=e.id,
                )
            )
        episodic_hits.sort(key=lambda h: h.score, reverse=True)

        ordered = procedural_hits + strategy_hits + episodic_hits
        picked: list[RetrievalHit] = []
        used_chars = 0
        for h in ordered:
            if len(picked) >= max_results:
                break
            chunk = len(h.body)
            if used_chars + chunk > char_budget and picked:
                continue
            if used_chars + chunk > char_budget and not picked:
                body = h.body[: max(0, char_budget - used_chars)]
                if body.strip():
                    picked.append(
                        RetrievalHit(
                            layer=h.layer,
                            score=h.score,
                            title=h.title,
                            body=body,
                            source_ref=h.source_ref,
                        )
                    )
                break
            picked.append(h)
            used_chars += chunk
        return picked

    def append_procedural(self, entry: ProceduralEntry) -> None:
        path = self.memory_dir / "procedural.ndjson"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        self._procedural.append(entry)

    def append_episodic(self, entry: EpisodicEntry) -> None:
        path = self.memory_dir / "episodic.ndjson"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
        self._episodic.append(entry)

    def rewrite_procedural(self, entries: list[ProceduralEntry]) -> None:
        """Replace ``procedural.ndjson`` atomically (temp file + replace)."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        path = self.memory_dir / "procedural.ndjson"
        tmp = path.with_suffix(".ndjson.tmp")
        text = "".join(
            json.dumps(e.model_dump(mode="json"), ensure_ascii=False) + "\n" for e in entries
        )
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        self._procedural = list(entries)
