# Restart Refined - Start Here

## Who This Is For
This guide is for engineers taking over implementation of the restart effort.

## What You Need To Know First
- The current system works but has high coupling and weak durability.
- The program is a **full rewrite** of the agent/runtime and debugger internals: new layout, new modules, and **permission to rename** anything that is not an external protocol or a published contract.
- **Behavior parity** (safety, legality, HITL, stale handling) is mandatory and proven with contracts + replay; **code-shape parity** with legacy is not a goal.
- LangGraph is the orchestration runtime, and typed contracts are mandatory.
- Local canonical telemetry target is SQLite; JSON logs are migration/export artifacts.

## Reading Paths

### Path A: 20-Minute Executive Pass
1. `01-product-and-scope.md`
2. `03-target-architecture.md`
3. `10-delivery-plan-and-quality-gates.md`

### Path B: Implementer (Core Runtime)
1. `02-current-system-baseline.md`
2. `03-target-architecture.md`
3. `04-runtime-behavior-and-safety.md`
4. `05-data-contracts.md`
5. `07-ai-and-model-integration.md`

### Path C: Implementer (Debugger/Observability)
1. `06-persistence-telemetry-and-replay.md`
2. `08-hitl-and-control-plane.md`
3. `09-frontend-debugger-ux.md`
4. `10-delivery-plan-and-quality-gates.md`

## System Goals
- Preserve command safety and operator experience.
- Remove god-module and process-local state bottlenecks.
- Improve reliability with checkpoints, idempotent events, and replay.
- Enable strategic+tactical collaboration and rich debugger streaming.

## Canonical Decisions (Locked)
- Multi-agent strategy planner is advisory-only.
- Planner triggers at combat start and long-term-impact decisions.
- Streaming contract is canonicalized across provider modes.
- Local canonical telemetry persistence is SQLite.
- Frontend debugger follows dual-theme design:
  - clean command-center default,
  - dense operator mode.

## Suggested First Week Plan For New Engineer
1. Reproduce a legacy run and capture **golden inputs/outputs** (or use existing logs) as parity references—not as a template for file layout.
2. Stand up the **new tree** and land the first vertical slice there (contracts + projection or dumb execute path).
3. Add/verify contract tests and replay parity fixtures against those goldens.
4. Validate one end-to-end scenario on the **new** control/debugger surface (even if minimal).
5. Record deviations, renames, and open decisions in `11-risk-register-and-open-decisions.md`.
