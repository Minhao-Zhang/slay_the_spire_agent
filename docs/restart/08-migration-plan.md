# Migration Plan

## Purpose
Define capability-by-capability delivery for the **greenfield rewrite**, with parity criteria and risk controls. This is a **build and validation plan** for the new system, not a promise to keep two production runtimes forever.

## Program stance
- **Rewrite:** Implement the target design in a new layout; internal naming, package structure, and APIs may differ from legacy wherever it improves clarity.
- **Cost accepted:** Schedule, full re-validation, operator re-training on any UX changes, and migration of fixtures/tooling to the new paths.
- **Invariant:** CommunicationMod and parity-critical safety semantics stay correct; everything else is allowed to change if tests and docs agree.

## Migration Strategy
- Use **vertical slices inside the new codebase** (still not an unreviewed big-bang merge).
- Keep the **game protocol** unchanged while replacing all agent/runtime internals.
- For each slice: implement in the new tree → test → replay/compare against golden fixtures or legacy oracle → accept.
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
| Strategic+tactical collaboration (advisory planner) | `src/agent/graph.py`, `src/main.py` | `decision_engine`, `agent_core` | trigger classifier tests + tactical alignment telemetry checks |
| Debugger frontend redesign (less clutter, higher utility) | `src/ui/templates/index.html`, `src/ui/templates/ai_debugger.html` | modularized `control_api` frontend | operator workflow tests + dashboard smoke + replay/trace usability checklist |
| Reasoning/output streaming to debugger (Responses + Completions compatibility) | `src/agent/graph.py`, `src/agent/llm_client.py`, `src/ui/dashboard.py` | `decision_engine`, `llm_gateway`, `control_api` | stream contract tests + reconnect/reorder edge-case tests + replay reconstruction checks |
| Canonical local telemetry store (SQLite) + history explorer | `logs/*.json`, `src/ui/dashboard.py`, `src/eval/replay.py` | `trace_telemetry`, `control_api`, `evaluation` | DB schema migration tests + idempotency/dedup checks + DB-backed replay parity |

## Slice Sequence
1. Core command/decision contracts and serializers.
2. State projection and legal action generator.
3. LangGraph state schema and checkpointer foundation.
4. Decision engine mode and proposal state machine on graph runtime.
5. HITL approval node/tool interrupts and typed `Command(resume=...)` flow.
6. Control API (operator/debugger surface) wired to interrupt/resume payloads; HTTP/WS routes may differ from legacy if contracts are versioned and documented.
7. LLM gateway and tool execution pipeline with structured-output fallback strategy.
8. Short-term/long-term memory layer with trim/summarize/store policy.
9. Trace telemetry and replay parity finalization.
10. Strategic planner advisory layer (combat-start + long-term-impact triggers) with tactical alignment telemetry.
11. Debugger frontend redesign rollout (command-center default + dense operator mode), validated in shadow mode before cutover.
12. Canonical reasoning/output stream pipeline rollout with OpenAI API mode compatibility and edge-case hardening.
13. SQLite canonical telemetry rollout with dual-write parity window and debugger history explorer cutover.

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
- Until **cutover**, keep the legacy app runnable **as a comparison oracle** (local runs, fixture generation), not as an indefinite architectural crutch.
- Use **feature flags inside the new system** for risky subsystems (planner, streaming modes, SQLite cutover) where that helps; do not rely on “flip back to old `main.py` forever.”
- If a slice fails parity: **fix forward** in the new code or **revert the change**; avoid expanding scope of dead legacy code.

## Final Cutover Criteria
- All capability rows implemented in the new codebase with passing parity checks.
- Legacy runtime **retired** from normal use; kept only as archived reference if needed.
- Restart documentation updated to reflect **live** naming, layout, and operational runbooks.
