# Restart Refined Documentation

Use this folder as the primary onboarding and implementation reference for the restart program.

## Program stance (authoritative summary)
- **Greenfield rewrite:** Build a **new codebase** (or a clearly separated new package tree) to the target architecture. We are **not** optimizing for a permanent side-by-side legacy runtime.
- **Willing to pay the cost:** Longer calendar time, full re-validation, breaking internal APIs, and operator-facing changes where the UX is genuinely better—documented and gated by tests.
- **Naming and layout are negotiable:** Module names, `src/` layout, and UI structure in these docs are **defaults**. Rename when it improves clarity; keep **external protocol** (CommunicationMod) and **published contracts** (telemetry schemas, public HTTP/WS where applicable) explicit and versioned when they change.
- **Legacy code:** Use as **oracle and fixture source** until cutover; after cutover, **archive/reference only**.

## Recommended First Read
1. `00-start-here.md`
2. `01-product-and-scope.md`
3. `03-target-architecture.md`
4. `10-delivery-plan-and-quality-gates.md`

## Full Document Set
- `00-start-here.md`
- `01-product-and-scope.md`
- `02-current-system-baseline.md`
- `03-target-architecture.md`
- `04-runtime-behavior-and-safety.md`
- `05-data-contracts.md`
- `06-persistence-telemetry-and-replay.md`
- `07-ai-and-model-integration.md`
- `08-hitl-and-control-plane.md`
- `09-frontend-debugger-ux.md`
- `10-delivery-plan-and-quality-gates.md`
- `11-risk-register-and-open-decisions.md`
- `12-glossary.md`

## Relationship To `docs/restart`
- `docs/restart` remains the detailed source/spec history.
- `docs/restart_refined` reorganizes that content for faster onboarding and execution.
- Both trees follow the same **rewrite stance** above; if conflicts are found, update both and record the decision in `11-risk-register-and-open-decisions.md` (or a short ADR).
