# Runtime Decision Loop Spec

## Purpose
Define parity-critical runtime loop behavior currently implemented in `src/main.py` so the restart can preserve command safety and operator experience.

## Scope
- Command selection and emission order.
- AI proposal lifecycle guards (timeout/stale/failure streak).
- Short-circuit actions that bypass LLM calls.
- Multi-command sequence execution policy.
- Proposal retry behavior requirements.
- Strategic planner collaboration trigger policy (restart target).

## State Identity and Freshness
- `state_id` is deterministic content identity (hash of normalized ingress payload), not monotonic.
- A proposal is stale when:
  - game state advances to a new `state_id`, or
  - queued sequence context (`turn_key`) no longer matches current turn context.
- Stale proposals or stale queued commands must not execute.

## Command Selection Precedence (Current)
1. **Queued sequence command** (if valid against current legal actions).
2. **Auto short-circuit command** (gold reward, single-action, confirm/cancel set).
3. **Manual command** from control plane queue.
4. **Approved AI command** (propose mode) or auto-approved proposal (auto mode).
5. **Idle fallback**:
   - `WAIT 10` if `wait` is available,
   - else `state` if available.
6. **Ready deadlock fallback**:
   - if `ready_for_command` and no command resolved, emit `state`.

## Idle and Deadlock Fallback Rules
- Preferred idle heartbeat command is `WAIT 10`.
- If `WAIT 10` is unavailable and `state` is available, request `state`.
- If `ready_for_command` and all resolution paths fail, force `state` as deadlock prevention.

## Proposal Lifecycle Guards (Current)
- Exactly one active proposal worker at a time.
- Timeout invalidates in-flight proposal and increments failure streak.
- Worker crash increments failure streak.
- Success resets failure streak.
- At configured failure streak limit, AI degrades to manual-safe mode.
- Proposal for an old `state_id` is discarded when game advances.

## Short-Circuit Rules (Current)
- **Combat reward gold auto-pick**:
  - on `COMBAT_REWARD`, if deterministic gold reward maps to legal `choose <idx>`, execute immediately.
- **Single legal action**:
  - if exactly one legal action exists, create proposal trace without LLM; auto mode executes immediately.
- **Confirm/cancel auto-confirm**:
  - if non-system legal actions are subset of `{CONFIRM, CANCEL}` and `CONFIRM` exists, select `CONFIRM` without LLM.
- **Queued sequence drain first**:
  - while valid queued command exists, execute it before any new LLM proposal.

## Multi-Command Sequence Behavior (Current)
- LLM may return `chosen_commands` sequence.
- First command is executed after approval/auto-approval.
- Remaining commands are queued as token-based sequence metadata.
- Before each queued execution:
  - resolve command against current legal actions,
  - for token PLAY, resolve token to canonical numeric play against current hand/targets.
- Queue is cleared when:
  - command cannot be resolved on current state, or
  - turn context changes (`turn_key` mismatch), or
  - command failure is reported by game.

## Command Failure Handling (Current)
- If ingress state reports command failure, latest AI execution trace is marked failed.
- Failed execution invalidates pending sequence and clears last execution context.
- Runtime falls back to normal proposal/manual flow on next valid state.

## Proposal Retry Requirement (Planned)
- Add control API action to request "repropose for current state" without mutating game state.
- Retry semantics:
  - keep same `state_id`,
  - create new `proposal_id`/`decision_id`,
  - link trace to prior proposal via `retry_of`.
- UI requirement:
  - add "Retry Proposal" control for current pending/invalid/rejected proposal.

## Strategic Planner Collaboration (Planned Restart Behavior)
- Planner authority is advisory; tactical command legality and final selection remain safety-gated by current validation rules.
- Planner trigger conditions:
  - beginning of each combat,
  - decisions classified as long-term impact.
- Tactical step consumes active strategic guidance context and records whether it followed or diverged from plan intent.
- Divergence must include a reason code in telemetry for replay and review.
- Planner failure/timeout must degrade to tactical-only flow for that decision cycle.

## LangGraph Mapping Guidance
- Keep ingress event debouncing/stability gating in `decision_engine` before LLM node entry.
- Use typed state reducers for any concurrently updated fields.
- If fan-out branches are used, define explicit reducers and fan-in barriers (`defer` nodes when needed).
- HITL can be inserted before expensive LLM work:
  - optional pre-proposal interrupt gate for operator-controlled modes.
- Resume paths must preserve same `thread_id` and typed resume payloads.

## Stable-State Gating Options (Design Choice)
- **Option A: Frame-based debounce**
  - Require `N` consecutive identical `state_id` observations (or unchanged legal actions hash) before calling LLM.
  - Suggested default candidate: 20 frames.
- **Option B: Time-based debounce**
  - Require stable state for `T` milliseconds before proposal start.
- **Option C: Hybrid**
  - Start proposal only when either frame or time threshold is satisfied and no in-flight proposal exists.
- Recommendation:
  - implement Option C with config flags so thresholds are tunable per environment.

## Context7 References (Validated)
- LangGraph parallel execution and reducers: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- LangGraph workflows and fan-out/fan-in patterns: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- LangGraph interrupts and approval routing: https://docs.langchain.com/oss/python/langgraph/interrupts
