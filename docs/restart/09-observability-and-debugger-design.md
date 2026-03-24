# Observability and Debugger Dashboard Design

## Purpose
Define a practical, production-ready logging format and debugger dashboard specification for the restart.

## Design Decision
- Use a **hybrid observability model**:
  - **Canonical**: project-owned structured event logs (required for replay/parity).
  - **Secondary**: LangSmith/Langfuse trace export (optional but recommended).
- Never make external tracing the only source of truth for command safety or replay analytics.
- Canonical event append must be idempotent and reconcilable with checkpoint history.

## Logging Format (Canonical)

### Event Envelope (Required on every record)
- `event_id` (UUID/ULID)
- `timestamp` (ISO-8601 UTC)
- `level` (`DEBUG|INFO|WARN|ERROR`)
- `event_type` (enum)
- `run_id`
- `thread_id` (LangGraph thread)
- `state_id`
- `turn_key`
- `proposal_id` (optional)
- `decision_id` (optional)
- `trace_id` / `span_id` (if available)
- `schema_version`

### Event Body (Typed by `event_type`)
- `state_ingested`
- `projection_completed`
- `proposal_started`
- `proposal_completed`
- `proposal_invalid`
- `interrupt_issued`
- `interrupt_resumed`
- `approval_applied`
- `command_validated`
- `command_executed`
- `command_failed`
- `checkpoint_written`
- `checkpoint_restored`
- `checkpoint_history_viewed`
- `thread_deleted`
- `memory_read`
- `memory_written`
- `mode_changed`

### Example (shape only)
```json
{
  "event_id": "01J123...",
  "timestamp": "2026-03-24T16:00:00Z",
  "level": "INFO",
  "event_type": "command_executed",
  "run_id": "2026-03-24-16-00",
  "thread_id": "spire-run-1",
  "state_id": "abc123",
  "turn_key": "F12-T3-COMBAT",
  "proposal_id": "p-001",
  "decision_id": "d-042",
  "schema_version": "1.0.0",
  "payload": {
    "command": "PLAY 1 0",
    "source": "ai-auto",
    "latency_ms": 812
  }
}
```

## Correlation and Semantics
- Follow OpenTelemetry-compatible correlation fields where possible (`trace_id`, `span_id`, resource/service fields).
- Keep a stable in-house event taxonomy to protect replay tooling from vendor schema changes.

## Redaction and Security
- Never log secrets, tokens, API keys, or full private prompts by default.
- Store only prompt hashes/previews unless debug mode is explicitly enabled.
- Separate operator-visible and internal-only fields.

## Debugger Dashboard Design

### Primary Views
- **Live Run Overview**
  - mode, floor/turn, health/status, proposal status, checkpoint status.
- **Decision Timeline**
  - ordered event stream with filters (`event_type`, `state_id`, severity, source).
- **Proposal Inspector**
  - prompt summary, model output, validation reasoning, chosen command(s).
- **Approval Queue**
  - evidence pack + three actions: approve / edit+approve / reject.
- **Execution Outcomes**
  - command success/failure table with retry and stale-state markers.

### Evidence Pack (for approvals)
- Current state snapshot summary.
- Candidate action and alternatives.
- Validation result and risk flags.
- Diff from last executed command context.
- Timeout countdown and escalation owner.
- Interrupt metadata (`interrupt_id`, `thread_id`, checkpoint id, allowed decisions).

### Required Interactions
- Filter + full-text search over timeline.
- Drill-down from event -> full payload JSON.
- Jump by `state_id`, `proposal_id`, or `decision_id`.
- Compare two decision attempts for same `state_id`.
- Replay from checkpoint for debugging.
- Resume an interrupt with typed decisions (`approve`, `edit`, `reject`, `feedback`) and show the exact resume payload.
- Stream inspector for LangGraph v2 chunks (`type`, `ns`, `data`) with interrupt detection in update streams.
- Multi-interrupt resolution UI that maps each interrupt id to its response payload.

## Performance Targets
- Live refresh <= 1s for critical status widgets.
- Timeline filter operations <= 200ms on active run.
- Event ingestion should be append-only and non-blocking.

## Retention and Storage
- Hot logs for recent runs, cold archive for older runs.
- Sidecar compatibility retained for replay evaluator migration.
- Schema-versioned migration rules for historical events.
- Keep checkpoint/state-view audit trails for operator access actions.
- If checkpoint write succeeds and event append fails, emit recovery marker and reconcile from outbox before declaring run healthy.

## Quality Gates for Observability
- All critical runtime transitions emit at least one required event.
- Event payloads validate against JSON schema in CI.
- Replay tests verify event completeness for key scenarios.
- Dashboard smoke tests validate approval flow and event drill-down.

## LangGraph HITL Best-Practice Requirements
- HITL pauses must be produced through LangGraph `interrupt(...)` (node/tool level), not custom blocking loops.
- Resumption must always use `Command(resume=...)` with the same `thread_id`.
- Approval decisions must be typed and schema-validated before resume.
- Durable checkpointer is required in non-dev environments; in-memory checkpointer is dev/test only.
- Approval node should route via explicit graph transitions (`proceed`/`cancel`/`revise`) after resume.
- All interrupt and resume events must be audit-logged with actor identity and timestamp.

## Implementation Sequence
1. Define event schemas and validator.
2. Build logger interface with sink fan-out (file + optional LangSmith/Langfuse).
3. Instrument graph nodes and checkpoint hooks.
4. Implement timeline-first dashboard.
5. Add approval evidence pack and replay drill-down.
