# Debugger Frontend Redesign Spec

## Purpose
Define a complete UI redesign for the debugger frontend that is less cluttered, more operationally useful, and aligned with restart architecture and observability goals.

## Product Direction (Locked)
- Workflow priority: **balanced** (fast operations + deep debugging).
- Visual direction: **dual theme**:
  - clean command-center default for daily use,
  - dense operator mode for high-throughput debugging sessions.

## Design Goals
- Reduce cognitive load during live runs.
- Preserve immediate access to approve/reject/edit workflows.
- Make trace forensics and replay navigation first-class.
- Keep strategic+tactical collaboration signals visible without overwhelming the main UI.
- Support long sessions with consistent keyboard and focus behavior.

## Existing UI Audit (Current Features to Preserve)
Current feature surface from `index.html` and `ai_debugger.html`:
- Live game dashboard: header stats, hand/piles, monsters, powers, inventory, non-combat screen rendering.
- Manual action controls and legal action button strip.
- AI controls: mode switch, approve/reject, optional edited action, latest proposal details.
- Trace visibility: recent traces list, summary metrics, parsed proposal/validation, response text, reasoning summary.
- Deep technical view: exact LLM call history and message payloads.
- Runtime status: websocket connectivity and AI status messages.
- Replay: run selector, step controls, jump-to-index, replay status.
- Session log with category filters (`state`, `action`, `system`, `error`, `replay`).
- Existing AI debugger route (`/ai`) and main dashboard route (`/`).

## Current Pain Points (Redesign Targets)
- Too many equal-weight panels compete for attention.
- Operational actions and forensic details are mixed in the same visual hierarchy.
- Important state transitions are hard to scan under high event volume.
- Trace browsing relies on long scrolling without strong grouping/filtering.
- Dense inline styles and monolithic templates reduce maintainability and consistency.

## Primary Information Architecture
Use a three-level structure with progressive disclosure:

1. **Run Command Bar (always visible)**
   - run identity, connection health, mode, floor/turn, proposal status, interrupt count.
   - top-level actions: approve, edit+approve, reject, retry proposal (when available).

2. **Operational Workspace (default focus)**
   - left: decision queue/timeline (recent proposals and interrupts).
   - center: evidence pack for selected decision.
   - right: action rail (approval actions, mode controls, quick guardrails).

3. **Analysis Workspace (tabbed)**
   - event timeline
   - LLM call inspector
   - replay + checkpoint tools
   - payload JSON explorer
   - strategic plan alignment history

## Screen Model

### A) Main Debugger (`/`)
Acts as command center with dual-pane operational focus:
- **Top command bar**: persistent run health and global controls.
- **Decision inbox**: prioritized items (`awaiting_approval`, `invalid`, `error`, `stale`).
- **Evidence pack panel**:
  - state summary,
  - candidate command(s),
  - validation result,
  - risk flags,
  - strategic plan alignment status.
- **Action rail**:
  - approve / edit+approve / reject / feedback (if enabled),
  - mode control,
  - follow-latest toggle.
- **Context drawer** (collapsible):
  - prompt preview,
  - response preview,
  - reasoning summary.

### B) Deep Debugger (`/ai`)
Specialized forensic surface:
- **Trace explorer** with saved filter presets.
- **LLM round viewer** with message grouping and diff between rounds.
- **Structured decision inspector** (proposal/validation/final decision/execution outcome).
- **Strategic plan panel**:
  - active plan,
  - trigger reason,
  - horizon,
  - tactical alignment (`followed`, `partially_followed`, `diverged`) and reason.
- **Raw event JSON drawer** for exact payload inspection.

### C) Replay Workspace (integrated tab, no context switch required)
- run selector, scrubber, jump, play/pause stepping.
- compare selected replay step against latest live state when live mode is active.
- optional branch comparison surface for checkpoint forks (restart target).

### D) History Explorer Workspace (DB-backed)
- run/thread tree navigator sourced from canonical telemetry DB.
- event timeline with structured filters and saved presets.
- decision-centric view (status, approval state, final command, latency, model).
- checkpoint lineage + interrupt lifecycle inspector.
- stream reconstruction panel (text/reasoning/tool/update lanes from `stream_events`).

## Dual-Theme Specification

### Theme 1: Clean Command-Center (default)
- Larger spacing, lower simultaneous panel count.
- Strong card hierarchy and progressive disclosure.
- Minimal always-on text; details opened on demand.
- Primary use: routine operation and quick interventions.

### Theme 2: Dense Operator Mode
- Compact spacing and reduced chrome.
- More columns visible simultaneously.
- Inline metadata and condensed typography.
- Primary use: incident response and replay triage.

### Theme Behavior Rules
- Theme switch is immediate and persistent per operator session.
- Theme affects layout density and visibility defaults, not data semantics.
- Keyboard shortcuts and action ordering remain identical across themes.

## Core Interaction Flows

### Flow 1: Approve Fast
1. New proposal enters decision inbox.
2. Evidence pack auto-focuses high-signal fields.
3. Operator approves/edit+approves/rejects via action rail.
4. Outcome status and event confirmation appear inline and in timeline.

### Flow 2: Investigate Failure
1. Operator selects failed/invalid decision.
2. Inspector highlights validation error and legal actions at that moment.
3. Operator opens LLM round diff and payload JSON.
4. Optional replay jump to same `state_id` and compare branch behavior.

### Flow 3: Strategic/Tactical Alignment Review
1. Operator opens decision with strategic guidance.
2. UI shows active strategic plan and trigger reason.
3. Tactical alignment marker and divergence reason (if any) are shown.
4. Timeline filter supports `tactical_plan_alignment_recorded`.

## Feature Requirements (Functional)

### FR1: Decision Inbox
- Group by status and urgency.
- Show minimal row schema: `decision_id`, `state_id`, status, command candidate, age.
- Pin interrupted decisions at top until resolved.

### FR2: Evidence Pack
- Must include:
  - state snapshot summary,
  - candidate and alternatives,
  - validation details,
  - risk flags,
  - timeout countdown,
  - interrupt metadata.

### FR3: Approval Surface
- Approve/reject/edit are keyboard and mouse accessible.
- Explicit confirmation for high-risk edits (configurable).
- Stale protection messaging must be specific and actionable.

### FR4: Timeline and Filters
- Full-text search + structured filters (`event_type`, `state_id`, `decision_id`, severity, source).
- Save/load operator filter presets.
- Jump links from inbox rows to timeline context.

### FR5: Replay and Checkpoint Tooling
- Existing replay stepping preserved.
- Add checkpoint metadata visibility (`thread_id`, `checkpoint_id`, `checkpoint_ns`) for restart.
- Replay UI must not block live updates; mode indicator required.

### FR7: DB History Explorer
- Must support paged/virtualized loading for large event sets.
- Must support correlation jumps by `state_id`, `decision_id`, `checkpoint_id`, `interrupt_id`.
- Must provide raw JSON payload drill-down per event row.
- Must provide saved query presets and recent query history.

### FR6: Strategic Planner Visibility
- Display planner trigger (`combat_start` or `long_term_impact`).
- Display plan horizon and active plan id.
- Display alignment status and divergence reason when present.

## Non-Functional Requirements (UX and Quality)

### NFR1: Performance
- Critical status updates visible within 1s of websocket message.
- Inbox interactions and filter changes <= 200ms in active runs.

### NFR2: Accessibility
- Full keyboard navigation for inbox, action rail, tabbed analysis panes.
- Visible focus states and sufficient contrast in both themes.
- No color-only status encoding; include text/icon labels.

### NFR3: Reliability
- UI degrades gracefully on websocket disconnect/reconnect.
- Replay and live data boundaries are explicit to avoid operator mistakes.

### NFR4: Maintainability
- Redesign spec assumes eventual split from monolithic inline CSS/JS templates into modular assets during implementation phase.
- Shared component vocabulary must be documented and reused across `/` and `/ai`.

## Component Inventory (Target)
- `RunCommandBar`
- `DecisionInbox`
- `EvidencePack`
- `ActionRail`
- `StatusChips`
- `TimelinePanel`
- `LlmCallInspector`
- `ReplayWorkbench`
- `JsonPayloadDrawer`
- `StrategicAlignmentPanel`
- `SessionLogPanel`

## Data Contract Mapping (UI Inputs)
- Existing:
  - `/api/ai/state`
  - websocket events (`state`, `agent_trace`, `ai_status`, `agent_mode`, `action`, `log`)
  - replay endpoints (`/api/runs`, `/api/runs/{run}`)
- Restart additions expected:
  - planner/alignment events,
  - checkpoint metadata fields in event payloads,
  - interrupt-id mapped multi-resume metadata.
  - canonical DB query endpoints for runs/threads/events/decisions/stream events.

## Migration and Rollout Plan
1. **Spec phase** (this doc + observability alignment).
2. **Wireframe phase**:
   - command-center default theme wireframes,
   - dense operator mode wireframes.
3. **Interaction prototype phase**:
   - decision inbox,
   - evidence pack,
   - timeline drill-down.
4. **Implementation phase** in restart frontend architecture.
5. **DB-backed history explorer phase** with query APIs and timeline virtualization.
6. **Shadow mode validation** against legacy UI during parity testing.
7. **Cutover** after quality gates and operator acceptance checklist pass.

## Acceptance Criteria
- Operators can approve/reject from inbox in <= 2 interactions.
- Failed decision investigation path can be completed without leaving debugger surface.
- Replay and live modes are clearly distinguishable and safely switchable.
- Strategic alignment context is visible for planner-enabled decisions.
- Both themes pass the same functional test suite and accessibility checks.

## Out of Scope (This Spec)
- Backend contract rewrites.
- New auth system behavior beyond existing restart security requirements.
- Replacing replay evaluator logic.
