"""Process-default trace store for the control API."""

from __future__ import annotations

import os

from src.trace_telemetry.store import InMemoryTraceStore

_app_store: InMemoryTraceStore | None = None


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


def get_app_trace_store() -> InMemoryTraceStore:
    global _app_store
    if _app_store is None:
        _app_store = InMemoryTraceStore(max_events=trace_max_events())
    return _app_store


def reset_app_trace_store_for_tests() -> None:
    global _app_store
    _app_store = None
