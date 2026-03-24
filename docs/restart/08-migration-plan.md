# Migration Plan

## Purpose

Define **staged delivery** for the **full greenfield rewrite**: what ships in order, and **how you prove each stage works** before starting the next. This complements the capability matrix and [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Program stance

- **Full rewrite:** Production behavior lives in the **new** package tree. Internal naming, layout, and HTTP/WebSocket routes may differ from legacy; contracts and tests are the source of truth.
- **Legacy:** The old `src/` runtime may remain available **only** during development as a **fixture/oracle generator** (replay logs, behavior comparison)—not as a long-term dual stack in production.
- **Invariant:** CommunicationMod protocol and parity-critical safety semantics (legal commands, stale handling, HITL) stay correct under test.
- **Gating:** No stage is “done” until its **verification** subsection passes. Do not rely on a big-bang integration at the end.

## Migration strategy

- **Vertical slices** inside the new codebase, each ending in **automated proof** (and manual checks only where unavoidable).
- **Game protocol** unchanged at the wire; everything above the adapter is replaceable.
- **Debug UI early:** ship a **minimal** `apps/web` + `control_api` slice as soon as projection exists so you can **see** parsed state, `state_id`, and legal actions (fixtures + live game) before LangGraph, LLM, or full operator UX.
- **LangGraph soon after:** compiled graph, checkpointer, and `thread_id` before real LLM and heavy product features.

## Capability matrix

| Capability | Current Owner | Target Owner | Parity / quality checks |
| --- | --- | --- | --- |
| Command grammar + legal action mapping | `src/ui/state_processor.py`, `src/agent/policy.py` | `state_projection`, `agent_core` | contract tests + command resolution tests |
| Mode orchestration (`manual/propose/auto`) | `src/main.py`, `src/ui/dashboard.py` | `decision_engine`, `control_api` | integration tests for mode transitions |
| Proposal lifecycle + stale handling | `src/main.py`, `src/agent/graph.py` | `decision_engine`, `agent_core` | timeout/stale replay fixtures |
| UI/control-plane APIs | `src/ui/dashboard.py` | `control_api` | endpoint contract tests + WS event snapshots |
| LLM/tool loop | `src/agent/graph.py`, `src/agent/llm_client.py`, `src/agent/tool_registry.py` | `agent_core`, `llm_gateway` | mocked LLM tests + tool loop fixtures |
| Human approval + edit workflow | `src/main.py`, `src/ui/dashboard.py` | `decision_engine`, `control_api` | interrupt/resume tests + stale-approval rejection tests |
| Trace + replay analytics | `src/agent/schemas.py`, `src/agent/tracing.py`, `src/eval/replay.py` | `trace_telemetry`, `evaluation` | replay metric deltas within threshold |
| Thread memory and cross-thread memory | `src/agent/session_state.py` | `decision_engine`, store-backed memory nodes | memory continuity tests + token budget regression tests |
| Runtime loop semantics (fallback, short-circuits, queue policy) | `src/main.py` | `decision_engine` | executable parity spec + integration fixtures |
| Proposal retry UX (same-context repropose) | `src/ui/dashboard.py`, `src/main.py` | `control_api`, `decision_engine` | API contract test + manual UX acceptance |
| Strategic+tactical collaboration (advisory planner) | `src/agent/graph.py`, `src/main.py` | `decision_engine`, `agent_core` | trigger classifier tests + tactical alignment telemetry checks |
| Debugger frontend | `src/ui/templates/index.html`, `src/ui/templates/ai_debugger.html` | `apps/web` (Vite + React + TS + Tailwind) + `control_api` | operator workflow tests + dashboard smoke + trace usability checklist |
| Reasoning/output streaming to debugger | `src/agent/graph.py`, `src/agent/llm_client.py`, `src/ui/dashboard.py` | `decision_engine`, `llm_gateway`, `control_api` | stream contract tests + reconnect/reorder edge-case tests + replay reconstruction checks |
| Canonical local telemetry (SQLite) + history explorer | `logs/*.json`, `src/ui/dashboard.py`, `src/eval/replay.py` | `trace_telemetry`, `control_api`, `evaluation` | DB schema migration tests + idempotency/dedup checks + DB-backed replay parity |

## Implementation stages (sequential)

Each stage has **scope**, **verification** (must all pass), and **gate** (exit criteria). Stages build on previous ones; skip-forward only for spikes, not for “done.”

**Two UI milestones:** (A) **Stage 3 — state debug shell** for parsing/projection. (B) **Stage 12 — full operator UI** per [`14-debugger-frontend-redesign-spec.md`](14-debugger-frontend-redesign-spec.md) after core flows exist. Between them, extend `apps/web` incrementally (approval in Stage 6, traces when available).

### Stage 1 — Contracts and serialization spine

- **Scope:** Versioned DTOs for ingress, projection outputs, legal actions, proposals, execution decisions, trace events; JSON/schema fixtures; deterministic `state_id` canonicalization per [`03-contracts-and-data-models.md`](03-contracts-and-data-models.md).
- **Verification:** Unit tests on serializers and canonicalization; no `Any` at public boundaries; `compileall` (or project equivalent) clean for new packages.
- **Gate:** Fixtures checked in; breaking schema change requires version bump and test update.

### Stage 2 — State projection and legal actions

- **Scope:** Pure `state_projection` from typed ingress to decision + UI view models; deterministic legal-action list; no I/O.
- **Verification:** Golden tests from recorded CommunicationMod payloads (or synthetic fixtures): same inputs → same `state_id`, same legal actions; property tests where useful.
- **Gate:** Projection and legality tests green; failures block all later stages.

### Stage 3 — Early debug UI, control API, and game ingest (no LangGraph, no LLM)

- **Scope:** Minimal **`apps/web`** (Vite + React + TS + Tailwind): **state debugger**—show raw ingress (or normalized JSON), projected view model, `state_id`, legal actions; optional side-by-side diff vs a pinned fixture. **`control_api`:** REST + WebSocket to push `state` updates. **`game_adapter` (read path)** + thin runner: CommunicationMod → parse → `state_projection` → broadcast (no AI, no graph). Optional dev endpoint to load a fixture for regression without the game.
- **Verification:** **Automated:** API + WS contract tests, snapshot of one fixture round-trip. **Manual:** run against Slay the Spire + CommMod and confirm on-screen state matches expectations (screens, combat, actions). **Optional:** compare key fields to legacy-oracle output for the same log line.
- **Gate:** You trust **visual + test** verification of parsing/projection before investing in orchestration. No LangGraph requirement in this stage.

### Stage 4 — LangGraph shell, checkpointer, thread identity

- **Scope:** Minimal `StateGraph`: ingest → project nodes (or equivalent), `AgentRuntimeState` wiring, checkpointer (`thread_id`), compile + short-run invocation from tests **without** real LLM (stub nodes). Reuse Stage 3 UI by feeding the **same** projection payloads from the graph path where possible.
- **Verification:** Tests: graph compiles; invoke with fixed `thread_id`; save and reload checkpoint; resume after trivial interrupt if modeled.
- **Gate:** Checkpoint round-trip and thread binding proven in CI.

### Stage 5 — Decision engine: modes and proposal lifecycle (no live LLM)

- **Scope:** `manual` / `propose` / `auto` policy; proposal state machine (idle → running → awaiting_approval → executed / stale / error); timeouts and stale rules using `state_id` correlation; **mocked** or canned proposal outputs.
- **Verification:** Integration tests for mode transitions, stale discard, and failure streak behavior against fixtures; no network in CI for this stage if possible.
- **Gate:** Full proposal lifecycle covered by tests; metrics match thresholds on replay fixtures when compared to legacy-oracle outputs where applicable.

### Stage 6 — HITL: interrupts, resume, minimal approval UI

- **Scope:** LangGraph `interrupt(...)` at approval boundary; `Command(resume=...)` with typed decisions; extend **`control_api`** for approve / edit+approve / reject; extend **`apps/web`** with **minimal** approval controls (not the full redesign yet).
- **Verification:** Tests: interrupt → resume → graph routes; stale-approval rejection; WS event snapshots for one golden scenario; manual smoke: approve/reject in browser.
- **Gate:** All HITL paths automated; approval usable from UI at least at MVP level.

### Stage 7 — LLM gateway and agent core

- **Scope:** `llm_gateway` (retries, routing, structured output strategies); `agent_core` parses to typed proposal, resolves to legal command with fallback order; tool loop if required by design.
- **Verification:** Mocked provider tests; contract tests for structured output; integration test with stub server or recorded responses; failure and timeout handling.
- **Gate:** No mandatory live API for CI; real-key smoke optional before Stage 8.

### Stage 8 — Game adapter write path and full command loop

- **Scope:** `game_adapter` **emit** validated commands to CommunicationMod; wire graph/decision completion to adapter; single legal command per decision; integrate with runner loop.
- **Verification:** Integration or scripted run with CommMod; assert commands ∈ legal list; short recorded session regression if available.
- **Gate:** Repeatable E2E from game state → decision → **command out** in the **new** tree.

### Stage 9 — Memory layer

- **Scope:** Short-term state in graph; long-term store-backed tools/nodes per [`11-memory-strategy.md`](11-memory-strategy.md); trim/summarize policy.
- **Verification:** Memory continuity tests across super-steps; namespace/thread rules; token budget tests if specified.
- **Gate:** Memory tests pass; no unbounded growth in fixtures.

### Stage 10 — Trace telemetry and evaluation

- **Scope:** `trace_telemetry` event append (schema-versioned); integration with `evaluation` / replay runner; deterministic replay mode for CI.
- **Verification:** Replay on golden logs: metrics within thresholds; critical events present; idempotency keys respected where specified.
- **Gate:** Replay job is a merge-blocking check for touched areas.

### Stage 11 — Strategic planner (advisory)

- **Scope:** Trigger classifier; planner node; `StrategicPlan` in state; tactical node with alignment telemetry per [`13-strategic-planner-collaboration.md`](13-strategic-planner-collaboration.md); feature flag default off until stable.
- **Verification:** Trigger tests; planner failure → tactical-only degradation; alignment event contract tests.
- **Gate:** Planner off by default does not change legality tests from earlier stages.

### Stage 12 — Full operator UI + streaming (debugger)

- **Scope:** Bring **`apps/web`** up to the **full** operator/debugger experience per [`14-debugger-frontend-redesign-spec.md`](14-debugger-frontend-redesign-spec.md) (layouts, dual theme, inbox, replay workbench as specified). **Streaming:** canonical lanes per [`15-streaming-reasoning-and-output-spec.md`](15-streaming-reasoning-and-output-spec.md); Responses + Completions compatibility; WS reorder/reconnect handling where applicable.
- **Verification:** UI tests or Playwright for critical flows; stream contract tests; manual checklist for dense operator mode; production build served or proxied against API.
- **Gate:** Operator workflows and debugger streams stable enough for daily use; no release with broken WS contract for core events.

### Stage 13 — SQLite canonical telemetry and history explorer

- **Scope:** SQLite schema, migrations, dual-write or cutover plan per [`16-sqlite-telemetry-and-history-explorer-spec.md`](16-sqlite-telemetry-and-history-explorer-spec.md); history explorer views in UI backed by DB.
- **Verification:** Migration tests; dedup/idempotency; DB-backed replay parity with file-based golden period.
- **Gate:** Explorer read path stable; no data loss on restart scenarios covered by tests.

## Cross-stage acceptance (every stage)

- Contracts touched in that stage are versioned; tests updated in the same change.
- Import/compile smoke for new code per [`07-quality-gates.md`](07-quality-gates.md).
- For graph-affecting stages: checkpoint resume validated where applicable.
- For HITL-affecting stages: interrupt → resume → route validated.
- For UI-affecting stages: automated smoke where feasible; manual checklist when listed for that stage.
- No stage closed on “works on my machine” alone unless manual checklist is explicitly listed for that stage and signed off.

## Rollback and safety

- **Fix forward** in the new codebase; revert a bad merge rather than expanding legacy.
- **Feature flags** in the **new** system for planner, streaming modes, SQLite cutover—so you can validate stage by stage without maintaining two architectures.
- Legacy runtime: use only for **generating or comparing fixtures** until cutover, then archive.

## Final cutover criteria

- Stages 1–**10** (minimum) complete with gates passed; stages 11–13 per product priority but documented if deferred.
- All capability rows intended for v1 have owners in the new tree and listed checks passing.
- Legacy **retired** from normal operation; restart docs and runbooks describe the **new** layout only.
