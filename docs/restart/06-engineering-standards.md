# Engineering Standards

## Purpose
Define non-negotiable software engineering practices for the rewrite.

## Naming and codebase conventions
- Prefer **clear, consistent names** over matching legacy (`main.py`, `dashboard`, etc.).
- Cross-module **contract names** (`IngressState`, `AgentRuntimeState`, …) should stay stable once published to tests and telemetry; internal module paths are **not** frozen by these docs.
- When renaming affects operators or integrators (HTTP paths, env vars), treat it as a **versioned surface** (changelog + `.env.example` + doc update).

## Build Baseline
- Primary near-term requirement: runtime code must compile/import cleanly and start successfully in the target environment.
- Optional quality tooling (lint/type/unit coverage) is recommended but not merge-blocking during early migration.
- Keep build/start commands stable and documented so contributors can validate changes quickly.

## Coding Standards
- Python version pinned for project and CI.
- Type hints required for all public interfaces.
- No `dict[str, Any]` in cross-module boundaries; use typed models.
- Functions that transform state must be pure and deterministic.
- Side effects only at adapters (I/O, network, storage, model calls).
- LangChain/LangGraph abstractions must be wrapped behind project interfaces (no framework leakage into domain contracts).

## Error Handling Standards
- Use structured error taxonomy:
  - `DomainError` (business invariant violation)
  - `AdapterError` (protocol/network/storage failures)
  - `PolicyError` (invalid model output or irrecoverable decision state)
- Do not silently swallow exceptions except in explicitly documented non-critical paths.
- Every recoverable error must emit structured telemetry with reason code.

## Observability Standards
- Structured JSON logs with fields: `timestamp`, `level`, `module`, `event`, `state_id`, `decision_id`, `run_id`.
- Correlation ids propagate across adapter, decision, and trace events.
- Trace schema versioned and backward compatible for replay tooling.
- Checkpoint metadata is logged for each interrupt/resume cycle.

## Configuration Standards
- Single source of truth config model with validation at startup.
- Environment variable schema documented in `.env.example`.
- Separate profiles: `dev`, `test`, `prod-like-local`.
- Fail fast for missing required secrets in AI-enabled modes.
- Configure structured output mode by environment:
  - `provider` (LangChain `ProviderStrategy`)
  - `tool` (LangChain `ToolStrategy`)

## Security Standards
- Mutating control endpoints must be protected outside local mode.
- Local mode explicitly binds to localhost by default.
- Secrets never logged.
- Add secret scanning in CI.
- WebSocket channels must enforce the same authn/authz policy as HTTP mutating endpoints.
- Define and enforce CORS/CSRF policy for browser-driven operator actions.
- Apply per-endpoint rate limits for mutation and resume/retry operations.
- Role model must be explicit (`viewer`, `operator`, `admin`) with least-privilege defaults.

## Governance Docs to Add
- `CONTRIBUTING.md`
- `docs/adr/template.md`
- `docs/definition-of-done.md`

## Framework-Specific Standards
- Prefer LangGraph `StateGraph` over ad-hoc threading for orchestration.
- Human approval gates must use graph interrupts/resume, not mutable global queues.
- State schemas must be explicit typed objects for graph state and node I/O.
- Long-term memory access must go through approved store-backed tool interfaces.
- Use one canonical runtime state type; do not handcraft ad-hoc per-node full state dicts.
- Node implementations must return partial updates only; ownership boundaries must be documented.
- Interrupt payloads and resume payloads must be JSON-serializable and deterministic in order.
- Do not place `interrupt(...)` inside broad `try/except` blocks.
- Avoid non-idempotent side effects before an `interrupt(...)`; place side effects after approval or in downstream nodes.
- Any node with multiple interrupts must preserve stable interrupt ordering across resumptions.
- Strategic planner outputs are advisory by default; tactical command legality and final command emission remain independent safety checks.

## Persistence and Threading Standards
- For graph runs that use a checkpointer, every invocation must include `thread_id` in configurable runtime config.
- Durable checkpointer is mandatory outside dev/test.
- State history (`get_state_history`) and latest snapshot (`get_state`) must be exposed through debugger APIs.
- `update_state` use must be restricted, audited, and role-gated.
- Checkpoint encryption should be enabled in environments handling sensitive data.

## Definition of Done (Rewrite Slices)
- Feature has typed contracts.
- Compile/import smoke checks pass for touched modules.
- Contract tests updated where fixtures already exist.
- Telemetry emits expected events.
- Documentation updated in `docs/restart`.
- Failure-path verification for timeout/stale/resume can be manual or automated during early migration.
- If slice mutates command selection, replay parity fixtures should be updated when available.

## Context7 References (Validated)
- LangGraph persistence API behavior (`thread_id`, `get_state`, checkpoints): https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupt/resume operational guidance and safety patterns: https://docs.langchain.com/oss/python/langgraph/interrupts
