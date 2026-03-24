# SQLite Telemetry and History Explorer Spec

## Purpose
Define the canonical local telemetry storage model using SQLite and specify debugger history exploration capabilities backed by that store.

## Scope
- Canonical local persistence for game state + AI/runtime telemetry.
- Schema, indexes, retention, and write ordering.
- Migration impact to existing JSON sidecar flow.
- Debugger UI requirements for history exploration.

## Decision
- Local/dev canonical telemetry store: **SQLite**.
- Production canonical telemetry store: **Postgres** (same logical schema).
- JSON logs remain as:
  - optional export artifact,
  - replay fixture source during migration,
  - emergency fallback when DB writes are unavailable.

## Design Principles
- Append-first event logging with idempotent writes.
- Canonical event envelope as source of truth.
- Materialized query tables for fast debugger UX.
- Replay reconstruction must be deterministic from DB.

## Canonical Write Path
For critical transitions:
1. compute transition decision.
2. persist checkpoint/runtime state boundary (where applicable).
3. append canonical event row with idempotency key.
4. append stream event rows (if streaming active).
5. enqueue outbox recovery marker if any append step fails after checkpoint success.

This preserves recovery truth while maintaining analytics/audit fidelity.

## SQLite Logical Schema

### `runs`
- `run_id` (PK)
- `started_at`, `ended_at`
- `profile` (`dev`, `test`, `prod-like-local`)
- `character`, `seed`, `status`
- `metadata_json`

### `threads`
- `thread_id` (PK)
- `run_id` (FK -> runs)
- `created_at`, `updated_at`
- `last_checkpoint_id`
- `current_state_id`
- `status`
- `metadata_json`

### `events` (canonical)
- `event_id` (PK)
- `idempotency_key` (UNIQUE)
- `timestamp`
- `level`
- `event_type`
- `run_id` (indexed)
- `thread_id` (indexed)
- `state_id` (indexed, nullable)
- `turn_key` (nullable)
- `proposal_id` (indexed, nullable)
- `decision_id` (indexed, nullable)
- `interrupt_id` (indexed, nullable)
- `checkpoint_id` (indexed, nullable)
- `checkpoint_ns` (nullable)
- `trace_id`, `span_id` (nullable)
- `schema_version`
- `payload_json` (TEXT JSON)

### `stream_events`
- `stream_event_id` (PK or composite with thread)
- `run_id`, `thread_id`, `decision_id`, `state_id`
- `timestamp`
- `stream_type` (`updates`, `messages`, `custom`)
- `sequence_no`
- `reordered` (bool)
- `partial` (bool)
- `usage_status` (`complete`, `incomplete`, `unknown`)
- `payload_json`

### `decisions` (materialized/derived index)
- `decision_id` (PK)
- `run_id`, `thread_id`, `state_id`
- `proposal_id`
- `status`
- `approval_status`
- `final_command`
- `latency_ms`
- `model_name`
- `created_at`, `updated_at`
- `summary_json`

### `interrupts`
- `interrupt_id` (PK)
- `run_id`, `thread_id`, `decision_id`
- `status` (`pending`, `approved`, `edited`, `rejected`, `stale`)
- `issued_at`, `resumed_at`
- `resume_action`
- `actor_id`
- `payload_json`

### `checkpoints`
- `checkpoint_id` (PK)
- `thread_id`
- `parent_checkpoint_id` (nullable)
- `checkpoint_ns`
- `created_at`
- `summary_json`

### `planner_alignment`
- `decision_id` (PK/FK -> decisions)
- `plan_id`
- `trigger_reason` (`combat_start`, `long_term_impact`)
- `alignment_status` (`followed`, `partially_followed`, `diverged`)
- `divergence_reason_code` (nullable)
- `payload_json`

### `outbox_recovery`
- `recovery_id` (PK)
- `run_id`, `thread_id`
- `checkpoint_id`
- `event_type`
- `payload_json`
- `status` (`pending`, `replayed`, `failed`)
- `created_at`, `updated_at`

## Required Indexes
- `events(run_id, timestamp)`
- `events(thread_id, timestamp)`
- `events(event_type, timestamp)`
- `events(state_id)`
- `events(decision_id)`
- `events(checkpoint_id)`
- unique `events(idempotency_key)`
- `stream_events(thread_id, decision_id, sequence_no)`
- `decisions(run_id, created_at)`
- `interrupts(thread_id, status)`

## Retention and Archival
- Hot window in SQLite for active local analysis (configurable days/runs).
- Cold export as:
  - compressed JSON bundles, or
  - archived DB snapshots.
- Retention jobs must never delete rows required by unresolved outbox recovery records.

## Migration From Current JSON Logs
1. Keep existing JSON emission path during migration.
2. Introduce dual-write mode:
   - write SQLite canonical rows,
   - continue sidecar JSON writes.
3. Validate parity using replay comparison from both sources.
4. Flip canonical-read path in debugger to SQLite.
5. Make JSON optional export/fallback only after stability period.

## Failure and Recovery Rules
- If SQLite write fails before event append:
  - do not claim event committed.
- If checkpoint write succeeds but event append fails:
  - write outbox recovery marker,
  - surface degraded health state in debugger.
- If stream event write fails:
  - keep canonical event row and mark stream lane partial.
- Any DB corruption detection:
  - freeze mutating debugger operations,
  - switch to read-only degraded mode,
  - emit explicit operator banner.

## Debugger History Explorer Requirements

### Primary Capabilities
- Run explorer:
  - filter by date, character, seed, status.
- Thread explorer:
  - active/stale/deleted threads, checkpoint summary.
- Decision timeline:
  - fast filter on status, event type, decision id, state id.
- Event inspector:
  - structured payload plus raw JSON view.
- Stream inspector:
  - reconstructed text/reasoning/tool lanes from `stream_events`.
- Checkpoint navigator:
  - lineage view and branch comparisons.
- Interrupt manager view:
  - pending/resumed/stale grouped by `interrupt_id`.

### Query UX Requirements
- saved filter presets:
  - failed decisions,
  - stale proposals,
  - missing usage chunks,
  - planner divergence cases.
- pagination/virtualization for large event sets.
- direct jump from event row to related decision/checkpoint/interrupt.

### Visual/Usability Requirements
- dual theme compatibility:
  - clean command-center default,
  - dense operator mode.
- sticky filter/query header.
- compact event row with expandable payload.
- color + text status encoding (never color-only).

## Security and Privacy
- redact sensitive fields before writing payloads that can contain secrets.
- profile-based reasoning visibility:
  - local: full/near-full depending on debug mode,
  - remote/prod-like: summary/redacted by default.
- audit all `update_state` and replay-fork operations.

## Quality Gates

### DB Integrity
- schema migration checks on startup.
- idempotency uniqueness validation.
- FK integrity checks for run/thread/decision relations.

### Behavioral
- replay reconstruction parity from SQLite vs canonical event stream.
- reconnect/reorder/dedup behavior in stream persistence.
- stale decision suppression correctness after state advance.

### UX
- history explorer smoke tests:
  - load run,
  - filter timeline,
  - open payload,
  - navigate checkpoint lineage.

## Implementation Slices
1. schema + migration framework.
2. canonical event writes + idempotency keys.
3. stream event persistence and partial/fallback markers.
4. debugger read APIs against SQLite query service.
5. history explorer UI with virtualized timeline.
6. dual-write parity window and cutover.

## Related Specs
- `docs/restart/09-observability-and-debugger-design.md`
- `docs/restart/10-langgraph-persistence-and-hitl-ops.md`
- `docs/restart/14-debugger-frontend-redesign-spec.md`
- `docs/restart/15-streaming-reasoning-and-output-spec.md`
