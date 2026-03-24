# Migration Plan

## Purpose
Define capability-by-capability migration with parity criteria and risk controls.

## Migration Strategy
- Use vertical slices, not big-bang replacement.
- Keep the game protocol unchanged while replacing internals.
- For each slice: implement -> test -> replay compare -> accept.
- Introduce LangGraph runtime early so approval, retry, and state transitions are graph-native.

## Capability Matrix

| Capability | Current Owner | Target Owner | Parity Checks |
| --- | --- | --- | --- |
| Command grammar + legal action mapping | `src/ui/state_processor.py`, `src/agent/policy.py` | `state_projection`, `agent_core` | contract tests + command resolution tests |
| Mode orchestration (`manual/propose/auto`) | `src/main.py`, `src/ui/dashboard.py` | `decision_engine`, `control_api` | integration tests for mode transitions |
| Proposal lifecycle + stale handling | `src/main.py`, `src/agent/graph.py` | `decision_engine`, `agent_core` | timeout/stale replay fixtures |
| UI/control-plane APIs | `src/ui/dashboard.py` | `control_api` | endpoint contract tests + WS event snapshots |
| LLM/tool loop | `src/agent/graph.py`, `src/agent/llm_client.py`, `src/agent/tool_registry.py` | `agent_core`, `llm_gateway` | mocked LLM tests + tool loop fixtures |
| Human approval + edit workflow | `src/main.py`, `src/ui/dashboard.py` | `decision_engine`, `control_api` | interrupt/resume tests + stale-approval rejection tests |
| Trace + replay analytics | `src/agent/schemas.py`, `src/agent/tracing.py`, `src/eval/replay.py` | `trace_telemetry`, `evaluation` | replay metric deltas within threshold |
| Thread memory and cross-thread memory | `src/agent/session_state.py` | `decision_engine`, `store-backed memory nodes` | memory continuity tests + token budget regression tests |
| Runtime loop semantics (fallback, short-circuits, queue policy) | `src/main.py` | `decision_engine` | executable parity spec + integration fixtures |
| Proposal retry UX (same-context repropose) | `src/ui/dashboard.py`, `src/main.py` | `control_api`, `decision_engine` | API contract test + manual UX acceptance |

## Slice Sequence
1. Core command/decision contracts and serializers.
2. State projection and legal action generator.
3. LangGraph state schema and checkpointer foundation.
4. Decision engine mode and proposal state machine on graph runtime.
5. HITL approval node/tool interrupts and typed `Command(resume=...)` flow.
6. Control API compatibility layer mapped directly to interrupt/resume payloads.
7. LLM gateway and tool execution pipeline with structured-output fallback strategy.
8. Short-term/long-term memory layer with trim/summarize/store policy.
9. Trace telemetry and replay parity finalization.

## Acceptance Criteria Per Slice
- Contracts finalized and versioned.
- Compile/import smoke checks pass for touched modules.
- Deterministic replay baseline does not regress critical metrics.
- Manual checklist pass on one end-to-end run.
- For graph slices: checkpoint resume and alternate-branch replay validated.
- For HITL slices: approve/edit/reject all validated via interrupt -> resume -> route transitions.
- For memory slice: thread continuity and cross-thread retrieval validated with stable namespaces.
- For runtime-loop slice: fallback command order, short-circuit gates, and queue stale-invalidation behavior match legacy outcomes.
- For retry UX slice: operator can request repropose for current state without mutating game state, and resulting trace links to original proposal.

## Rollback and Safety
- Keep legacy runtime path runnable until final cutover.
- Feature flags for each migrated subsystem.
- If parity fails, route traffic/commands back to legacy path.

## Final Cutover Criteria
- All capability rows migrated with passing parity checks.
- Legacy path no longer required for command safety.
- Restart documentation updated to `completed` state.
