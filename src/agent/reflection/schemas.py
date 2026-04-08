from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProceduralLessonDraft(BaseModel):
    lesson: str
    context_tags: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.6
    status: str | None = None


class EpisodicDraft(BaseModel):
    character: str = ""
    outcome: str = ""
    floor_reached: int | str = ""
    cause_of_death: str = ""
    deck_archetype: str = ""
    key_decisions: list[str] = Field(default_factory=list)
    run_summary: str = ""
    context_tags: dict[str, Any] = Field(default_factory=dict)


class ReflectionPersistInput(BaseModel):
    run_dir: str
    run_id: str
    procedural_lessons: list[ProceduralLessonDraft] = Field(default_factory=list)
    episodic: EpisodicDraft | None = None


class ReflectionPersistResult(BaseModel):
    procedural_appended: int = 0
    procedural_merged: int = 0
    episodic_appended: int = 0
    procedural_ids: list[str] = Field(default_factory=list)
    episodic_id: str | None = None
    procedural_skipped_empty: int = 0
    procedural_skipped_cap: int = 0
