# Frontend Debugger UX

## UX Objective
Create a debugger that supports both fast intervention and deep forensic analysis without overwhelming operators.

## Product Direction (Locked)
- Balanced workflow priority.
- Dual-theme UX:
  - clean command-center default,
  - dense operator mode.

## Workspace Model

### 1) Command Workspace
- run command bar (status, mode, health).
- decision inbox (priority statuses first).
- evidence pack (state, candidate, validation, risk).
- action rail (approve/edit/reject/feedback and mode controls).

### 2) Analysis Workspace
- timeline with filters + search.
- LLM call inspector.
- replay/checkpoint tools.
- payload JSON explorer.
- strategic alignment view.

### 3) History Explorer (DB-Backed)
- run/thread navigator.
- event timeline from canonical DB.
- checkpoint lineage explorer.
- interrupt lifecycle explorer.
- stream lane reconstruction view.

## Required Interaction Flows
- fast approve/edit/reject in <= 2 interactions.
- failed decision investigation without leaving debugger surface.
- replay jump and compare for same `state_id` or `decision_id`.
- strategic alignment review (`followed`/`partially_followed`/`diverged`).

## Data Inputs
- websocket: live state + event + stream envelopes.
- REST: current runtime state and control actions.
- DB query APIs: runs/threads/events/decisions/checkpoints/stream events.

## Performance and Accessibility
- critical status updates visible <= 1s.
- filter interactions <= 200ms for active run datasets.
- keyboard navigation across major panes.
- no color-only status coding.

## Visual System Guidelines
- clear hierarchy: command actions above forensic detail.
- compact rows with expandable details.
- sticky filter/query header in history views.
- consistent status chip semantics across themes.

## Implementation Guidance
- split monolithic templates into reusable components.
- keep shared component vocabulary between `/` and `/ai`.
- virtualize long lists/timelines to avoid UI stalls.
