# Delivery Plan and Quality Gates

## Delivery Strategy
- **Greenfield rewrite:** Implement vertical slices in the **new** codebase; prove behavior with contracts and replay.
- Legacy runtime remains available **until cutover** as an oracle and for fixture extraction—not as a permanent dual-production design.
- Feature-flag **risky subsystems inside the new stack** (planner, streaming profiles, SQLite cutover) where useful.

## Recommended Slice Order
1. Contracts and serializers.
2. State projection and legal action generation.
3. Graph state + checkpointer base.
4. Decision engine lifecycle and mode transitions.
5. HITL interrupt/resume flow.
6. Control API (operator/debugger surface; routes may differ from legacy if versioned).
7. LLM gateway and tool loop.
8. Memory layer.
9. Telemetry and replay parity.
10. Strategic planner advisory layer.
11. Debugger UX redesign.
12. Streaming reasoning/output pipeline.
13. SQLite canonical telemetry + history explorer cutover.

## Merge-Blocking Quality Gates

### Gate 1: Static Health
- compile/import smoke checks pass.
- runtime startup smoke path passes.
- graph compile/smoke with checkpointer passes.

### Gate 2: Automated Tests
- contract tests for payload compatibility and structured output.
- integration tests for HITL, stale-state, and mode transitions.
- streaming tests for reconnect/reorder/dedup and provider mode compatibility.
- DB tests for schema migration, idempotency, and integrity.

### Gate 3: Replay Regression
- deterministic replay scenarios pass:
  - combat targeted play,
  - map/event/shop/rest,
  - sequence stale interruption,
  - failure/retry,
  - checkpoint replay and branch behavior,
  - planner alignment telemetry,
  - missing usage/reasoning availability edge cases.

### Gate 4: CI Policy
- required checks must be green before merge.
- release branch runs expanded replay suite.

## Acceptance Criteria Per Slice
- typed contracts finalized.
- touched modules compile/import cleanly.
- parity metrics do not regress on critical thresholds.
- telemetry emits required events for changed capabilities.
- docs updated in `docs/restart_refined`.

## Rollback Policy
- If parity fails on a slice: **fix forward** in the new code, **revert** the offending change, or **disable** the feature flag for that subsystem in the new stack.
- Do not expand maintenance of legacy production paths as the default safety valve.

## Final Cutover Criteria
- All slices complete in the new codebase with passing parity checks.
- Legacy runtime **retired** from normal operation; kept only as archived reference if needed.
- `docs/restart_refined` and `docs/restart` describe **shipped** names, routes, and runbooks.
