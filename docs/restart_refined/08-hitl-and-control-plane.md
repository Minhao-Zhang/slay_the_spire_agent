# HITL and Control Plane

## Purpose
Define approval operations, interrupt/resume semantics, and control API behavior for safe human-in-the-loop operation.

## Control Plane Responsibilities
- expose mode/status/approval APIs,
- expose state/trace/history query APIs,
- bridge operator actions to graph resume commands,
- publish websocket updates for live debugger UI.

## Approval Primitive
- HITL pause must be `interrupt(...)`.
- Resume must be `Command(resume=...)` on the same `thread_id`.
- Supported decisions:
  - `approve`
  - `edit`
  - `reject`
  - `feedback`

## Interrupt Rules
- deterministic interrupt call ordering inside nodes.
- no broad try/except around interrupt flow.
- pre-interrupt side effects must be idempotent or deferred.
- concurrent interrupts require explicit interrupt-id mapping.

## Control API Safety Requirements
- stale proposal approvals must be rejected with actionable message.
- mutating actions are role-gated outside local mode.
- all mutating operations are audit logged.
- replay/update-state operations are privileged and reason-tagged.

## Mode and Command Controls
- runtime modes: `manual`, `propose`, `auto`.
- mode switch is explicit and observable.
- command approval can include edited action when policy allows.
- no implicit approvals from stream completion.

## Required API Surfaces (Target)
- AI state and mode endpoints.
- proposal approval/reject/edit endpoints.
- run/thread/history explorer query endpoints.
- checkpoint history and replay/fork endpoints.
- websocket stream for state/event/trace updates.

## Operator UX Requirements
- decision inbox with age/urgency.
- evidence pack with risk/validation details.
- clear stale-state and degraded-health banners.
- keyboard-accessible approve/edit/reject actions.

## Audit Events (Minimum)
- `interrupt_issued`
- `interrupt_resumed`
- `approval_applied`
- `mode_changed`
- `state_updated`
- `replay_started` / `replay_completed`
