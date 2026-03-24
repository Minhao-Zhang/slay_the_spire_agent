# Quality Gates

## Purpose
Define mandatory checks that block merges during the rewrite.

## Context
Gates apply to code in the **new** implementation tree as it replaces legacy. Module and path names in examples (`state_projection`, etc.) are illustrative—checks must follow whatever package layout ships, documented in the repo runbook.

## Gate 1: Static Quality
- Compile/import smoke check for touched runtime packages.
- No new TODO/FIXME in production code without issue reference.

### Command Contract (must be pinned in repo scripts)
- `python -m compileall src`
- App startup smoke command for local runtime (documented in repo runbook).
- Graph compile/smoke invocation with checkpointer enabled for migrated flows.

Optional lint/type/test tooling can be added incrementally and is not merge-blocking during early restart slices.

## Gate 2: Automated Testing
- Automated tests where available for:
  - `state_projection`
  - command parser/serializer
  - decision validation and fallback
- Integration tests where available for:
  - control API approval flow
  - proposal lifecycle timeout/stale behavior
  - interrupt/resume behavior for approve/edit/reject paths
  - multi-interrupt parallel resume behavior (interrupt-id mapping)
  - v2 stream interrupt detection path (`messages` + `updates`)
  - strategic planner trigger behavior (combat start + long-term-impact decisions)
  - planner failure degradation to tactical-only execution
  - debugger core operator workflows (approve, edit+approve, reject, replay step/jump)
  - reasoning/output streaming behavior for both OpenAI Responses API and Chat Completions API
  - stream reconnect/reorder/dedup behavior in websocket transport
  - SQLite telemetry write/read behavior under reconnect and partial-failure scenarios
- Contract tests where available for:
  - game adapter payload compatibility
  - UI VM shape and action list schema
  - structured output schema conformance (`ProviderStrategy` and `ToolStrategy` paths)
  - memory record schema for store reads/writes

## Gate 3: Replay Regression
- Deterministic fixture runs for key scenarios (merge-blocking):
  - combat turn with targeted play
  - map/event/shop/rest flows
  - multi-command sequence with stale-state interruption
  - command failure and retry path
  - checkpoint replay with interrupt resume and alternate branch
  - checkpoint history queries and operator state update actions
  - strategic+tactical alignment telemetry presence on planner-enabled runs
  - debugger UI smoke scenarios for timeline drill-down and evidence pack rendering
  - reasoning availability/absence scenarios and missing final usage chunk handling
  - SQLite-backed replay reconstruction parity against canonical event stream
- Compare key metrics against baseline:
  - legal action rate
  - invalid output rate
  - action execution success rate
- Stochastic live-model replay can run as non-blocking trend analysis and alert on sustained drift.

## Gate 4: CI Policy
- PR-required checks:
  - compile/import smoke check
  - deterministic replay regression subset
  - graph compile/smoke test with checkpointer enabled
  - persistence backend migration check (`setup` path for configured backend)
  - SQLite schema migration + integrity check for local canonical telemetry profile
- No direct merge without green checks.
- Release branch requires expanded replay suite.

## Coverage and Thresholds
- Coverage targets are deferred until a stable automated test baseline exists.
- Until then, require compile/import checks and replay parity checks for touched capabilities.

## Test Data Management
- Keep fixtures immutable and versioned.
- Add schema version with each fixture bundle.
- Use snapshot tests only for stable serialized contracts.
- Keep at least one fixture set per structured-output mode (`provider`, `tool`).
- Include fixtures for long-thread memory pressure (trim/summarize/delete policies).
