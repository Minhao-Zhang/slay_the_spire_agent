from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProceduralEntry(BaseModel):
    id: str
    created_at: str
    source_run: str = ""
    lesson: str
    context_tags: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    times_validated: int = 0
    times_contradicted: int = 0
    status: str = "active"


class EpisodicEntry(BaseModel):
    id: str
    run_dir: str = ""
    timestamp: str = ""
    character: str = ""
    outcome: str = ""
    floor_reached: int | str = ""
    cause_of_death: str = ""
    deck_archetype: str = ""
    key_decisions: list[str] | str = Field(default_factory=list)
    run_summary: str = ""
    context_tags: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextTags:
    act: str | None
    floor: int | None
    screen_type: str
    character: str
    ascension: int | None
    enemy_slugs: tuple[str, ...]
    event_slug: str
    relic_slugs: tuple[str, ...]
    flat_tags: frozenset[str]


MemoryLayer = Literal["strategy", "expert", "procedural", "episodic"]


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    layer: MemoryLayer
    score: float
    title: str
    body: str
    source_ref: str
