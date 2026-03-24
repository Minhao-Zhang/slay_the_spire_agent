# Runtime Behavior and Safety

## State Identity
- `state_id` is deterministic content hash, not monotonic.
- Stale detection must use `state_id` and `turn_key`, never sequence assumptions.

## Command Selection Precedence
1. Valid queued sequence command.
2. Auto short-circuit command (safe deterministic cases).
3. Manual command from control queue.
4. Approved AI command / auto-approved proposal.
5. Idle fallback (`WAIT 10` then `state`).
6. Ready deadlock fallback (`state`).

## Lifecycle Rules
- Single active proposal worker.
- Timeout/crash increments failure streak.
- Success resets failure streak.
- Failure streak threshold degrades mode to manual-safe.
- Proposal for old `state_id` must be discarded.

## Sequence Queue Rules
- LLM may return command sequence.
- Execute first command after approval/auto-approval.
- Queue rest with token metadata.
- Re-resolve each queued command against current legal actions.
- Clear queue on resolution failure, `turn_key` mismatch, or execution failure.

## Short-Circuit Rules
- Combat reward deterministic gold pick.
- Single legal action direct execution path.
- Confirm/cancel-only auto-confirm path.
- Queue-drain precedence over new LLM work.

## Proposal Retry (Planned)
- Repropose current state without mutating game state.
- Reuse `state_id`; generate new `proposal_id` and `decision_id`.
- Link retries with `retry_of`.

## Strategic Planner Integration (Planned)
- Planner is advisory only.
- Triggers:
  - start of combat,
  - long-term impact decisions.
- Tactical layer records `followed` / `partially_followed` / `diverged` + reason code.
- Planner failure degrades to tactical-only path.

## Safety Invariants
- No command executes without legal-action validation at execution time.
- Stream/telemetry data cannot imply execution authority.
- Stale proposals/streams cannot be approved for active execution.
- Interrupt resumes require same `thread_id` and typed payload validation.

## Failure Handling Policy
- Prefer fail-safe behavior over aggressive retries.
- On unresolved command path while ready, emit `state` to prevent deadlock.
- Emit structured telemetry for all recoverable failure transitions.
