# Restart documentation hub

This folder holds the **greenfield rewrite** plan: target architecture, legacy baseline, contracts, migration order, and deep specs (observability, persistence, UI, streaming, telemetry).

**Canonical architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md) — module boundaries, graph state, safety, monorepo UI notes, replay modes, and links to everything else. The former `05-target-architecture.md` was merged into it to avoid duplicate sources.

## Suggested reading order

1. **Stance and shape:** [`ARCHITECTURE.md`](ARCHITECTURE.md) — program goals, modules, flows, quality alignment.
2. **What exists today:** [`01-system-inventory.md`](01-system-inventory.md), [`02-feature-catalog.md`](02-feature-catalog.md).
3. **What must stay true:** [`03-contracts-and-data-models.md`](03-contracts-and-data-models.md), [`04-risk-register.md`](04-risk-register.md).
4. **How we build and ship:** [`TODO.md`](TODO.md) (bootstrap + stage checklist), [`06-engineering-standards.md`](06-engineering-standards.md), [`07-quality-gates.md`](07-quality-gates.md), [`08-migration-plan.md`](08-migration-plan.md).
5. **Runtime and agents:** [`12-runtime-decision-loop-spec.md`](12-runtime-decision-loop-spec.md), [`11-memory-strategy.md`](11-memory-strategy.md), [`13-strategic-planner-collaboration.md`](13-strategic-planner-collaboration.md).
6. **Operator experience and data plane:** [`09-observability-and-debugger-design.md`](09-observability-and-debugger-design.md), [`14-debugger-frontend-redesign-spec.md`](14-debugger-frontend-redesign-spec.md), [`15-streaming-reasoning-and-output-spec.md`](15-streaming-reasoning-and-output-spec.md), [`16-sqlite-telemetry-and-history-explorer-spec.md`](16-sqlite-telemetry-and-history-explorer-spec.md).
7. **Durable execution:** [`10-langgraph-persistence-and-hitl-ops.md`](10-langgraph-persistence-and-hitl-ops.md) — checkpoints, interrupts, replay governance (pairs with persistence sections in `ARCHITECTURE.md`).

## Document index

| File | Summary |
| --- | --- |
| [`TODO.md`](TODO.md) | Bootstrap checklist (Step 0: archive `src/`; Step 1: monorepo) + migration stage checkboxes |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Target architecture, module graph, graph state, security, replay/eval modes, related specs |
| [`01-system-inventory.md`](01-system-inventory.md) | Current codebase layout and integration points |
| [`02-feature-catalog.md`](02-feature-catalog.md) | User-visible and system features, paths, failures |
| [`03-contracts-and-data-models.md`](03-contracts-and-data-models.md) | Typed contracts and migration rules from legacy behavior |
| [`04-risk-register.md`](04-risk-register.md) | Program risks and mitigations |
| [`06-engineering-standards.md`](06-engineering-standards.md) | Coding and engineering standards |
| [`07-quality-gates.md`](07-quality-gates.md) | Merge-blocking checks |
| [`08-migration-plan.md`](08-migration-plan.md) | Capability matrix; staged plan with early `apps/web` state debugger (Stage 3) and verification gates |
| [`09-observability-and-debugger-design.md`](09-observability-and-debugger-design.md) | Canonical logging, debugger dashboard design |
| [`10-langgraph-persistence-and-hitl-ops.md`](10-langgraph-persistence-and-hitl-ops.md) | LangGraph persistence, HITL, replay/update-state |
| [`11-memory-strategy.md`](11-memory-strategy.md) | Short-term vs long-term memory |
| [`12-runtime-decision-loop-spec.md`](12-runtime-decision-loop-spec.md) | Decision loop semantics |
| [`13-strategic-planner-collaboration.md`](13-strategic-planner-collaboration.md) | Strategic planner and tactical alignment |
| [`14-debugger-frontend-redesign-spec.md`](14-debugger-frontend-redesign-spec.md) | Debugger UX, `apps/web` target stack |
| [`15-streaming-reasoning-and-output-spec.md`](15-streaming-reasoning-and-output-spec.md) | LLM streaming and debugger contracts |
| [`16-sqlite-telemetry-and-history-explorer-spec.md`](16-sqlite-telemetry-and-history-explorer-spec.md) | SQLite telemetry schema and history explorer |

Numbered filenames are for stable sorting; there is no `05-*.md` file (content lives in `ARCHITECTURE.md`).
