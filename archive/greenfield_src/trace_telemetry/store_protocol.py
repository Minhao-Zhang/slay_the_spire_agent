"""Trace store interface shared by in-memory and SQLite backends."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TraceStore(Protocol):
    def next_step_seq(self, thread_id: str) -> int: ...
    def append(self, event: dict[str, Any]) -> bool: ...
    def list_events(
        self,
        *,
        thread_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def list_thread_summaries(self) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...
