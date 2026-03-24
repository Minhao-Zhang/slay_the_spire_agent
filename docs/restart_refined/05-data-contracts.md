# Data Contracts

## Contract Philosophy
- Every cross-boundary interface is typed and versioned.
- No free-form dicts at module boundaries.
- DTO validation is required before state mutation or graph resume.

## Core Contracts
- `IngressState`: normalized game adapter payload.
- `ProjectedState`: decision model + UI model projection output.
- `LegalAction`: typed action candidate representation.
- `DecisionProposal`: model output schema.
- `ExecutionDecision`: chosen command + source + reason.
- `TraceEvent`: canonical telemetry event envelope.
- `AgentRuntimeState`: single graph state schema.

## Identity Contracts
- `state_id`: deterministic hash with explicit canonicalization rules/version.
- `turn_key`: contextual execution key for queue freshness checks.
- Correlation ids: `proposal_id`, `decision_id`, `interrupt_id`, `checkpoint_id`.

## Command Contracts
- Replace string-heavy protocol logic with typed command AST + serializer.
- Keep protocol serialization compatible with existing game command grammar.
- Preserve fallback semantics (`WAIT 10`, `state`).

## Validation Contracts
- Intent resolution and command emission are separate stages.
- Validation output includes confidence and reason code.
- Parse/validation errors are typed (`PolicyError`).

## Interrupt/Resume Contracts
- Interrupt payload contains evidence and allowed actions.
- Resume payload is typed and schema-validated before `Command(resume=...)`.
- Multi-interrupt resumes require interrupt-id to response mapping.

## Planner Contracts
- `StrategicPlan` is advisory only and cannot directly emit executable commands.
- Tactical decision records planner alignment status and optional divergence reason.

## Streaming Contracts
- Canonical stream envelope includes:
  - `stream_event_id`, `thread_id`, `decision_id`, `stream_type`, `payload`.
- `stream_type` is one of `updates`, `messages`, `custom`.
- `messages` blocks may include `text`, `reasoning`, `tool_call_chunk`.

## Telemetry Event Envelope
- Required fields: `event_id`, `timestamp`, `level`, `event_type`, `run_id`, `thread_id`, `schema_version`.
- Common optional correlation fields:
  - `state_id`, `turn_key`, `proposal_id`, `decision_id`, `interrupt_id`, `checkpoint_id`, `checkpoint_ns`.
- `payload` is typed by event type and schema version.
