# Streaming Reasoning and Output Spec

## Purpose
Define a complete, implementation-ready contract for streaming model output and reasoning to the debugger frontend in the restart architecture, with explicit edge-case handling.

## Scope
- LangGraph runtime streaming contract.
- OpenAI compatibility for:
  - Responses API
  - Chat Completions API
- Frontend event consumption model.
- Failure modes, recovery behavior, and test requirements.

## Goals
- Stream actionable model output to operators with low latency.
- Surface reasoning and tool-call progression where available.
- Keep one stable frontend contract regardless of provider/API mode.
- Preserve command safety and replayability.

## Non-Goals
- Defining provider-specific auth setup.
- Replacing canonical event logs with stream-only data.
- Exposing unsafe private reasoning in non-debug profiles.

## Architectural Decision
Use a two-layer streaming model:

1. **Canonical stream layer (required)** via LangGraph stream parts:
   - `updates` (node/state transitions)
   - `messages` (LLM output/message chunks)
   - `custom` (project-defined telemetry extras)

2. **Provider detail layer (optional)**:
   - OpenAI-specific metadata and raw event mapping attached to canonical `custom` events.

Frontend consumes only canonical events; provider-specific fields are optional extensions.

## Compatibility Summary

### OpenAI Responses API
- Preferred for rich typed output and reasoning compatibility.
- Supports event-style streaming and better structured content mapping.
- Recommended when reasoning stream visibility is a product requirement.

### OpenAI Chat Completions API
- Fully supported for output token streaming.
- Reasoning visibility may be reduced compared to Responses API depending on model/provider behavior.
- Token usage and reasoning-token totals are often finalized at end-of-stream usage payload.

## LangGraph Streaming Contract (Required)

Runtime must invoke graph streaming with v2 stream part format:
- `stream_mode=["updates","messages","custom"]`
- `version="v2"`

### Event Normalization Rule
Every streamed item forwarded to frontend must be transformed to:
- `stream_event_id` (monotonic per run/thread)
- `timestamp`
- `run_id`
- `thread_id`
- `state_id` (if known at emission time)
- `decision_id` (if known)
- `source` (`langgraph` | `provider_adapter`)
- `stream_type` (`updates` | `messages` | `custom`)
- `payload` (type-specific data)
- `schema_version`

## Canonical Stream Event Types

### 1) `updates` stream payload
- `node_name`
- `delta` (partial state update)
- `checkpoint_id` (if available)
- `checkpoint_ns` (if available)

Use cases:
- proposal lifecycle progress
- interrupt issuance/resume transitions
- tactical/strategic alignment updates

### 2) `messages` stream payload
- `channel` (`assistant` | `tool` | `system`)
- `content_blocks` (normalized list)
- `text_delta` (optional flattened text delta)
- `metadata` (node/tool/model context)

Supported `content_blocks` kinds:
- `text`
- `reasoning` (if available)
- `tool_call_chunk`
- `tool_result_chunk` (if surfaced through adapter pipeline)

### 3) `custom` stream payload
- project-defined structured telemetry:
  - `reasoning_usage_partial`
  - `provider_event`
  - `guardrail_event`
  - `stream_health`
  - `fallback_notice`

## Provider Mapping Rules

### Responses API -> Canonical
- map response text deltas to `messages.text`.
- map reasoning content to `messages.reasoning` when available.
- map provider event markers into `custom.provider_event`.
- map final usage summaries into `custom.reasoning_usage_partial` or final usage event.

### Chat Completions API -> Canonical
- map delta content to `messages.text`.
- if reasoning fields are absent in-stream, do not synthesize fake reasoning blocks.
- map final usage block (when present) to `custom.reasoning_usage_partial`.
- when usage chunk is missing (interrupted stream), mark usage as `incomplete`.

## Frontend Consumption Contract

### UI Zones
- **Live output lane**: `messages.text` deltas.
- **Reasoning lane**: `messages.reasoning` blocks (feature-gated by profile).
- **Tool lane**: `tool_call_chunk` and tool events.
- **State lane**: `updates` node transitions.
- **Health lane**: `custom.stream_health` + fallback notices.

### Ordering Rules
- Order by `stream_event_id` first, then `timestamp`.
- If out-of-order packet arrives, insert by id and mark `reordered=true`.
- UI must never assume strictly contiguous delivery for websocket transport.

### Deduplication Rules
- Dedup key: (`thread_id`, `decision_id`, `stream_event_id`).
- If duplicate arrives, ignore silently and increment internal duplicate metric.

## Edge Cases and Required Handling

### E1: Stream Interrupted Mid-Decision
Symptoms:
- websocket disconnect
- provider stream aborted

Handling:
- emit `custom.stream_health` with `status="degraded"`.
- keep partial text/reasoning visible and marked `partial=true`.
- keep decision in `running` or `interrupted` status until resume/fail terminal event.
- do not auto-approve or auto-reject due to stream interruption.

### E2: Missing Final Usage Chunk
Symptoms:
- no final token usage (common on interrupted stream)

Handling:
- set usage state to:
  - `usage_status="incomplete"`
  - `reasoning_tokens=null` (not zero)
- emit `custom.fallback_notice` with reason.
- replay analytics must treat as missing data, not zero-cost completion.

### E3: Reasoning Not Present for Model/API Mode
Symptoms:
- no reasoning blocks in streamed content

Handling:
- show lane status: `Reasoning unavailable for this model/API mode`.
- continue normal text and validation rendering.
- no warnings in local profile; info-level note only.

### E4: Out-of-Order Message and Update Events
Symptoms:
- update event arrives after later message chunk

Handling:
- reorder in UI buffer by `stream_event_id`.
- if reorder window exceeded (configurable), append as late event and mark `late_arrival=true`.
- preserve raw arrival sequence in debug drawer for diagnostics.

### E5: Duplicate Chunks
Symptoms:
- same chunk re-delivered after reconnect/retry

Handling:
- deduplicate by key; do not re-render duplicate text delta.
- count duplicate events for observability.

### E6: Stale Decision Stream Continues After State Advance
Symptoms:
- old decision continues streaming after `state_id` changed

Handling:
- mark stream context `stale=true`.
- stop forwarding old chunks to actionable approval panel.
- keep stale stream visible in forensic view only.
- emit `fallback_notice` with stale boundary metadata.

### E7: Multi-Interrupt Concurrent Streams
Symptoms:
- overlapping interrupts emitted across branches

Handling:
- render per-interrupt thread with explicit `interrupt_id`.
- require resume actions to bind to `interrupt_id` map.
- reject ambiguous resume without id mapping.

### E8: Provider Schema Drift
Symptoms:
- unexpected provider payload shape

Handling:
- adapter must fail-open to canonical minimum:
  - still emit raw text when possible
  - emit `provider_event` with `parse_error=true`
- never crash stream consumer due to non-critical parse mismatch.

### E9: Oversized Reasoning Payload
Symptoms:
- very large reasoning blocks degrade UI performance

Handling:
- apply truncation policy:
  - keep first `N` and last `M` chars
  - provide expand-on-demand in forensic view
- keep full content only in canonical logs if profile allows.

### E10: Sensitive Reasoning Exposure Risk
Symptoms:
- reasoning includes secrets or sensitive values

Handling:
- apply redaction profile before frontend emission in non-debug environments.
- default to summary-only reasoning outside local mode.
- log redaction actions as audit events.

## Safety and Governance
- No stream event can bypass command legality validation.
- Approval actions remain explicit operator/API actions, not implied by stream completion.
- Stream data is observability context, not execution authority.
- Reasoning display must be profile-gated (`local`, `remote-dev`, `prod`).

## Performance Requirements
- text delta render latency target: <= 250ms median from websocket receive.
- updates lane refresh: <= 500ms median.
- no main-thread freeze on 10k+ stream events in a run; virtualized timeline required in implementation.

## Persistence and Replay Requirements
- Every streamed event mapped to canonical event schema where applicable.
- Replay must reconstruct:
  - output deltas
  - reasoning availability flags
  - tool-call progression
  - stream interruption/fallback markers
- Event idempotency contract follows (`thread_id`, `checkpoint_id`, `event_type`, optional `stream_event_id`).
- Local canonical persistence for stream lanes should use SQLite `stream_events` and related correlation indexes as defined in `docs/restart/16-sqlite-telemetry-and-history-explorer-spec.md`.

## API/DTO Additions (Restart Contracts)
Add typed DTOs:
- `StreamEnvelope`
- `MessageContentBlock`
- `ReasoningAvailability`
- `UsageSummaryPartial`
- `StreamHealthEvent`
- `FallbackNotice`

All DTOs must be versioned and validated before frontend broadcast.

## Quality Gates and Tests

### Contract tests
- Responses API mapping -> canonical stream events.
- Chat Completions mapping -> canonical stream events.
- missing reasoning and missing usage handling semantics.

### Integration tests
- reconnect mid-stream with dedup and reorder correctness.
- stale stream suppression after state advance.
- multi-interrupt stream display and resume mapping.

### Replay tests
- replay parity with partial stream and missing usage chunks.
- deterministic reconstruction of event ordering with reorder markers.

### UI smoke tests
- live text streaming lane
- reasoning lane presence/absence behavior
- fallback/health banner rendering

## Rollout Plan
1. Introduce canonical stream DTOs behind feature flag.
2. Implement adapter mapping for Responses API first.
3. Add Chat Completions mapping parity.
4. Enable frontend lanes with profile-gated reasoning visibility.
5. Activate quality gates and replay coverage before default-on rollout.

## References (Context7-Validated)
- LangGraph streaming (`updates`, `messages`, `custom`, v2 stream parts).
- LangChain model content blocks and reasoning extraction in Python.
- OpenAI Responses and Chat Completions streaming behavior and usage chunk caveats.
