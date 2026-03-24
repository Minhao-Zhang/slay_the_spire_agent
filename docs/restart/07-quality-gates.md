# Quality Gates

## Purpose
Define mandatory checks that block merges during the rewrite.

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
