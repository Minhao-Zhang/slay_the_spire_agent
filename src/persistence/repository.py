"""Abstract repository for Phase 0 state shadowing."""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol


class StateRepository(Protocol):
    def create_run(self, payload: dict[str, Any]) -> None:
        """Idempotent upsert of ``runs`` (+ optional ``experiments`` / ``run_experiments``)."""

    def insert_frame(self, payload: dict[str, Any]) -> str:
        """Insert ``run_frames`` row; returns ``frame`` row id."""

    def upsert_decision_final(self, payload: dict[str, Any]) -> None:
        """Terminal ``agent_decisions`` snapshot for ``(run_id, event_index)``."""

    def upsert_run_end(self, payload: dict[str, Any]) -> None:
        """Upsert ``run_end`` for ``run_id``."""

    def record_llm_call(self, payload: dict[str, Any]) -> str:
        """Insert ``llm_call``; returns new row id."""

    def record_mutation_event(
        self,
        *,
        actor: str,
        target_kind: str,
        target_id: str,
        action: str,
        before: Any | None,
        after: Any | None,
        langfuse_trace_id: str | None = None,
    ) -> None:
        """Append-only audit row."""

    def mark_run_ended(self, run_id: str, *, ended_at: dt.datetime | None = None) -> None:
        """Set ``runs.status`` / ``ended_at`` when a session ends."""
