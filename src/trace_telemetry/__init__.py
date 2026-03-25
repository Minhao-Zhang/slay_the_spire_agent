"""Stage 10: schema-versioned agent-step traces (in-memory; SQLite in Stage 13)."""

from src.trace_telemetry.recorder import record_agent_invocation
from src.trace_telemetry.runtime import (
    get_app_trace_store,
    reset_app_trace_store_for_tests,
    trace_max_events,
    trace_recording_enabled,
)
from src.trace_telemetry.schema import TRACE_SCHEMA_VERSION, build_agent_step_event
from src.trace_telemetry.store import InMemoryTraceStore

__all__ = [
    "TRACE_SCHEMA_VERSION",
    "InMemoryTraceStore",
    "build_agent_step_event",
    "get_app_trace_store",
    "record_agent_invocation",
    "reset_app_trace_store_for_tests",
    "trace_max_events",
    "trace_recording_enabled",
]
