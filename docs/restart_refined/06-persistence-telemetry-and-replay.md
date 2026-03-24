# Persistence, Telemetry, and Replay

## Storage Model by Environment
- **Dev/test**:
  - checkpointer: `InMemorySaver` (unit) or `SqliteSaver` (durable local integration),
  - canonical telemetry: SQLite.
- **Production**:
  - checkpointer/store: Postgres variants,
  - canonical telemetry: Postgres with same logical schema.

## Canonical Local Telemetry (SQLite)
SQLite is the canonical local source of truth for:
- events,
- stream events,
- decisions,
- interrupts,
- checkpoints,
- planner alignment,
- outbox recovery.

JSON logs remain optional export/fallback and migration artifacts.

## Write Ordering Contract
For critical transitions:
1. compute transition,
2. checkpoint boundary write (if applicable),
3. canonical event append (idempotent),
4. stream event append (if active),
5. outbox marker on partial failure after checkpoint success.

## Idempotency and Dedup
- Event dedup key includes correlation context and transition identity.
- Replay consumers must tolerate at-least-once delivery.
- Stream dedup key includes `thread_id`, `decision_id`, `stream_event_id`.

## Replay Requirements
- Deterministic replay is merge-blocking.
- Replay reconstructs decision lifecycle, command legality, and key telemetry.
- Stream-aware replay reconstructs:
  - text deltas,
  - reasoning availability status,
  - tool-call progression,
  - interruption/fallback markers.

## Recovery and Fault Tolerance
- If checkpoint succeeds and event append fails:
  - write outbox recovery record,
  - mark run health degraded,
  - re-append asynchronously with idempotency protection.
- If stream append fails:
  - preserve canonical event,
  - mark stream partial and continue execution safely.

## Retention
- Hot local retention window in SQLite for active debugging.
- Cold archive via compressed exports or DB snapshot bundles.
- Do not purge records referenced by pending recovery rows.

## Observability Event Taxonomy (Minimum)
- state lifecycle: ingest/projection.
- proposal lifecycle: started/completed/invalid/stale.
- approval lifecycle: interrupt_issued/resumed/approval_applied.
- execution lifecycle: validated/executed/failed.
- persistence lifecycle: checkpoint_written/restored/history_viewed.
- streaming lifecycle: stream health/fallback/provider parse notices.
- planner lifecycle: strategic plan started/completed/failed + alignment.
