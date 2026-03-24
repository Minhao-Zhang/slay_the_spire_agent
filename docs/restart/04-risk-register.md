# Risk Register

## Purpose
Track the highest-risk engineering issues in the current codebase and define rewrite implications.

## Severity Legend
- High: likely to cause correctness/reliability regressions.
- Medium: maintainability/scalability risk.
- Low: optimization or process debt.

## Risks

### R1: Orchestrator God Module
- Severity: High
- Evidence: `src/main.py` combines I/O, scheduling, mode policy, validation flow, logging, retries.
- Impact: difficult testing and high regression probability.
- Rewrite Control: split into application services with explicit interfaces.

### R2: Process-Local Mutable Control State
- Severity: High
- Evidence: `src/ui/dashboard.py` global `ai_runtime` and `manual_actions_queue`.
- Impact: race conditions, no persistence, not multi-worker safe.
- Rewrite Control: state machine + persistent queue/store abstraction.

### R3: Stringly-Typed Commands and Status
- Severity: High
- Evidence: `command` free-form strings and status literals across modules.
- Impact: brittle validation and hidden edge cases.
- Rewrite Control: typed command model and finite state machine.

### R4: Tight UI/Backend Coupling
- Severity: Medium
- Evidence: UI depends on implicit VM/trace shapes and timing assumptions.
- Impact: schema changes break multiple layers.
- Rewrite Control: versioned API contracts and contract tests.

### R5: Broad Exception Swallowing
- Severity: Medium
- Evidence: multiple `except Exception` paths in main/dashboard update channels.
- Impact: silent failures reduce observability and diagnosis speed.
- Rewrite Control: standardized error handling and structured logs.

### R6: Monolithic Template Assets
- Severity: Medium
- Evidence: large in-template JS/CSS (`index.html`, `ai_debugger.html`).
- Impact: difficult review, testing, and modular evolution.
- Rewrite Control: componentized frontend modules and static asset pipeline.

### R7: Inconsistent Dependency Management
- Severity: Medium
- Evidence: docs mention `pyproject.toml`/`uv.lock`, repo currently uses `requirements.txt`.
- Impact: environment drift and onboarding friction.
- Rewrite Control: one canonical package strategy and lockfile.

### R8: Missing Quality Automation
- Severity: High
- Evidence: no CI, no test framework wiring, no lint/type enforcement.
- Impact: regressions likely during rewrite.
- Rewrite Control: quality gates mandatory before feature migration.

### R9: Security Posture for Control Endpoints
- Severity: Medium
- Evidence: mutating control endpoints unauthenticated.
- Impact: unsafe if exposed beyond localhost.
- Rewrite Control: explicit local-only mode + auth strategy for non-local deployments.
