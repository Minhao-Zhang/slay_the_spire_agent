"""Per-call context for LLM observability + SQL ``llm_call`` rows (Phase 0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LlmCallContext:
    """Optional; when fields are missing, recording is skipped or degraded."""

    run_id: str | None = None
    frame_id: str | None = None
    event_index: int | None = None
    state_id: str | None = None
    client_decision_id: str | None = None
    turn_key: str | None = None
    stage: str = "decision"
    round_index: int = 1
    prompt_profile: str = "default"
    experiment_id: str | None = None
    """32 lowercase hex chars; one trace per decision when using Langfuse."""
    langfuse_trace_id: str | None = None
    reasoning_effort: str | None = None
    #: When false, emit Langfuse only (no ``llm_call`` row) — e.g. reflector without a SQL ``runs`` row.
    mirror_llm_to_sql: bool = True
    tags: dict[str, Any] = field(default_factory=dict)
