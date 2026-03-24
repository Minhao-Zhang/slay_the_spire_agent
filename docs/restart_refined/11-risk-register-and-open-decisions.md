# Risk Register and Open Decisions

## Active Risks

### High
- Orchestration concentration risk (legacy coupling and regression hazard).
- Process-local mutable control state risk (non-durable, non-multi-worker safe).
- Stringly-typed command/status risk (hidden edge-case behavior).
- Missing automation risk (CI/test baseline still being built).
- **Full rewrite risk:** schedule slip, rediscovery of edge cases, and doc/code drift if naming or layout changes without updating both doc trees.

### Medium
- UI/backend implicit coupling risk.
- broad exception swallowing risk.
- monolithic frontend asset maintainability risk.
- control endpoint security posture risk outside localhost.

## Controls and Mitigations
- enforce module boundaries and typed contracts.
- move control state to graph/runtime persistence primitives.
- adopt canonical event/stream schema and DB-backed queryability.
- require merge-blocking replay and integration gates.
- add profile-based security controls and audit trails.

## Open Decisions (Track Here)
1. Stable-state gate defaults (`frame`, `time`, or hybrid threshold values).
2. Planner horizon evolution (`next_3_decisions` fixed vs adaptive policy).
3. Final production telemetry store query topology (single DB vs split concerns).
4. Reasoning redaction policy per deployment profile.
5. History explorer default retention window and archival cadence.
6. **Final package and public API naming** (top-level Python package, HTTP path prefix, env var prefixes)—choose before wide external integration; document in README and `.env.example`.

## Decision Log Template
- **Decision**:
- **Date**:
- **Owner**:
- **Context**:
- **Options considered**:
- **Chosen option**:
- **Impact**:
- **Rollback plan**:

## Escalation Triggers
- replay parity regression in merge-blocking scenarios.
- inability to reconstruct a decision timeline from canonical store.
- stale/interrupt safety violations in approval workflows.
- unresolved outbox recovery backlog above threshold.
