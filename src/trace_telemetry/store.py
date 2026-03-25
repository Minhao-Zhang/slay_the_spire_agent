"""In-memory append-only trace store (Stage 10; Stage 13 may persist to SQLite)."""

from __future__ import annotations

import threading
from typing import Any


class InMemoryTraceStore:
    def __init__(self, *, max_events: int = 10_000) -> None:
        self._max = max(1, int(max_events))
        self._events: list[dict[str, Any]] = []
        self._seq_by_thread: dict[str, int] = {}
        self._lock = threading.Lock()

    def next_step_seq(self, thread_id: str) -> int:
        with self._lock:
            n = self._seq_by_thread.get(thread_id, 0) + 1
            self._seq_by_thread[thread_id] = n
            return n

    def append(self, event: dict[str, Any]) -> bool:
        """
        Append event. If ``idempotency_key`` is present and matches a row still
        retained in the buffer, skip and return False (replay retry dedupe).
        """
        key = event.get("idempotency_key")
        if isinstance(key, str) and key:
            with self._lock:
                retained = {e.get("idempotency_key") for e in self._events}
                retained.discard(None)
                if key in retained:
                    return False
                self._push(event)
            return True
        with self._lock:
            self._push(event)
        return True

    def _push(self, event: dict[str, Any]) -> None:
        while len(self._events) >= self._max:
            self._events.pop(0)
        self._events.append(event)

    def list_events(self, *, thread_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            ev = list(self._events)
        if thread_id is None:
            return ev
        return [e for e in ev if e.get("thread_id") == thread_id]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._seq_by_thread.clear()
