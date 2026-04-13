"""Structured run summary for reflection (deterministic analyzer output)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    state_id: str = ""
    turn_key: str = ""
    status: str = ""
    final_decision: str | None = None
    planner_summary: str = ""
    llm_model_used: str = ""
    reasoning_effort_used: str = ""
    strategist_ran: bool = False
    lessons_retrieved: int = 0
    tool_names: list[str] = Field(default_factory=list)
    source_path: str = ""


class RunReport(BaseModel):
    run_dir: str
    timestamp: str = ""
    seed: str = ""
    character: str = ""
    ascension: int = 0
    victory: bool | None = None
    floor_reached: int = 0
    score: int = 0
    cause_of_death: str | None = None
    path_summary: list[str] = Field(default_factory=list)
    deck_changes: list[dict[str, Any]] = Field(default_factory=list)
    resource_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    key_combats: list[dict[str, Any]] = Field(default_factory=list)
    notable_decisions: list[dict[str, Any]] = Field(default_factory=list)
    total_ai_decisions: int = 0
    valid_rate: float = 0.0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    tool_usage: dict[str, int] = Field(default_factory=dict)
    decision_count: int = 0
    decisions: list[DecisionRecord] = Field(default_factory=list)
    run_end_derived: dict[str, Any] = Field(default_factory=dict)
    run_metrics_line_count: int = 0
    last_run_end_derived: dict[str, Any] = Field(default_factory=dict)
    deck_evolution_notes: list[str] = Field(default_factory=list)
    inflection_points: list[str] = Field(default_factory=list)
    mistakes: list[str] = Field(default_factory=list)
    retrieved_lesson_ids: list[str] = Field(default_factory=list)
