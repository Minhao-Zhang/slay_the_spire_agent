"""Schema-versioned agent-step traces: in-memory or SQLite (`SLAY_TRACE_BACKEND`)."""

from src.trace_telemetry.recorder import record_agent_invocation
from src.trace_telemetry.runtime import (
    get_app_trace_store,
    reset_app_trace_store_for_tests,
    shutdown_trace_store,
    trace_backend,
    trace_max_events,
    trace_recording_enabled,
)
from src.trace_telemetry.schema import TRACE_SCHEMA_VERSION, build_agent_step_event
from src.trace_telemetry.sqlite_store import SqliteTraceStore
from src.trace_telemetry.store import InMemoryTraceStore
from src.trace_telemetry.store_protocol import TraceStore

__all__ = [
    "TRACE_SCHEMA_VERSION",
    "InMemoryTraceStore",
    "SqliteTraceStore",
    "TraceStore",
    "build_agent_step_event",
    "get_app_trace_store",
    "record_agent_invocation",
    "reset_app_trace_store_for_tests",
    "shutdown_trace_store",
    "trace_backend",
    "trace_max_events",
    "trace_recording_enabled",
]
