# Product Goals and Scope

## Mission
Deliver a **new** Slay the Spire agent runtime and operator tooling that preserves **parity-critical** behavior (protocol, command safety, HITL) while improving correctness, maintainability, observability, and operator control.

## Why Restart Exists
Current implementation has concentrated orchestration logic, process-local mutable control state, and string-heavy contracts. This raises regression risk and limits multi-worker durability. The chosen response is a **greenfield rewrite**: we accept migration cost in exchange for a cleaner system end-to-end.

## Success Criteria
- All parity-critical runtime behaviors preserved (validated by tests and replay, not by preserving legacy module names).
- Typed contracts at cross-module boundaries.
- Durable orchestration with checkpoint/replay support.
- Human approval flow implemented with interrupt/resume primitives.
- Debugger supports live operations and deep forensic inspection.
- Deterministic replay gates protect command safety through the rewrite.
- **Naming and structure:** The shipped codebase may differ from these documents where clarity improves; docs and operator runbooks match what ships.

## In Scope
- **New** runtime and package layout following domain/adapters/interfaces boundaries (exact folder names are not fixed).
- LangGraph-based decision engine and lifecycle state machine.
- Strategic+tactical collaboration (advisory planner).
- Reasoning/output streaming to debugger with provider compatibility.
- Canonical local telemetry in SQLite and history exploration UI.
- Quality gates, replay fixtures, and vertical delivery slices **inside the new codebase**.
- Renaming modules, routes, and UI components when it reduces long-term confusion.

## Out Of Scope
- Changing external CommunicationMod protocol.
- Shipping a rewrite **without** parity validation for safety-critical paths (replay/contracts remain mandatory).
- Planner hard-policy enforcement in initial rollout.
- Production auth redesign beyond restart baseline controls.

## Stakeholders
- Runtime engineers (decision safety and orchestration).
- Frontend/debugger engineers (operator workflows).
- Evaluation/ML engineers (replay parity and drift analysis).
- Operators/reviewers approving or rejecting AI actions.

## Top-Level Deliverables
- Modular runtime package layout (final names may differ from early drafts in this repo).
- Canonical schema contracts and validators.
- Deterministic replay workflow and metrics.
- DB-backed telemetry query surfaces.
- Refined debugger UX with dual theme and history explorer.

## Price we accept
- Longer timeline than an incremental refactor in place.
- Rewriting tests, fixtures, and tooling against the new modules and APIs.
- Temporary duplication of effort (oracle legacy vs new tree) **only until cutover**, then retiring legacy from normal use.
