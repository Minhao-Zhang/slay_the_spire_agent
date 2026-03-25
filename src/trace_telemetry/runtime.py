"""Process-default trace store for the control API."""

from __future__ import annotations

import os

from src.trace_telemetry.sqlite_store import SqliteTraceStore
from src.trace_telemetry.store import InMemoryTraceStore
from src.trace_telemetry.store_protocol import TraceStore

_app_store: TraceStore | None = None


def trace_max_events() -> int:
    try:
        return max(1, min(int(os.environ.get("SLAY_TRACE_MAX_EVENTS", "10000")), 1_000_000))
    except ValueError:
        return 10_000


def trace_recording_enabled() -> bool:
    return os.environ.get("SLAY_TRACE_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def trace_backend() -> str:
    m = os.environ.get("SLAY_TRACE_BACKEND", "memory").strip().lower()
    return m if m in ("memory", "sqlite") else "memory"


def get_app_trace_store() -> TraceStore:
    global _app_store
    if _app_store is None:
        if trace_backend() == "sqlite":
            _app_store = SqliteTraceStore()
        else:
            _app_store = InMemoryTraceStore(max_events=trace_max_events())
    return _app_store


def reset_app_trace_store_for_tests() -> None:
    global _app_store
    if _app_store is not None:
        _app_store.close()
        _app_store = None


def shutdown_trace_store() -> None:
    """Close SQLite trace connection (FastAPI shutdown)."""
    reset_app_trace_store_for_tests()
