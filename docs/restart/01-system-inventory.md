# System Inventory

## Purpose
This document records the current runtime architecture, integration points, and module responsibilities so a rewrite can preserve behavior while reducing coupling.

## Runtime Flow
1. `src/main.py` reads raw CommunicationMod JSON from `stdin`.
2. `src/ui/state_processor.py` transforms raw state into a view model (VM) with legal actions and KB enrichment.
3. `src/main.py` posts state and telemetry to `src/ui/dashboard.py`.
4. `src/agent/graph.py` drives proposal generation through prompt assembly, model calls, tool loop, and validation.
5. `src/main.py` is the only execution boundary (`print(action)` to game process).
6. Raw state and sidecar AI logs are written under `logs/`; `src/eval/replay.py` analyzes them.

## Module Responsibilities

### Orchestration and Command Execution
- `src/main.py`
  - Run lifecycle, log run directories, state deduping.
  - Proposal worker lifecycle and timeout handling.
  - AI mode policy (`manual`, `propose`, `auto`).
  - Final command emission and queued sequence handling.

### Control Plane and Debug UI
- `src/ui/dashboard.py`
  - FastAPI REST/WebSocket endpoints.
  - In-memory control state (`ai_runtime`) and manual queue.
  - Trace update merge and stale trace marking.
- `src/ui/templates/index.html`, `src/ui/templates/ai_debugger.html`
  - Client rendering and operator interactions.

### Domain Projection
- `src/ui/state_processor.py`
  - Converts raw game state into VM.
  - Builds `actions` list used by UI and AI validation.
  - Adds knowledge-base enrichment to cards/relics/monsters/events/powers/potions.

### Agent Decision Pipeline
- `src/agent/graph.py`
  - Main decision graph, tool roundtrips, planner integration.
- `src/agent/prompt_builder.py`
  - Prompt sections and strategy/context assembly.
- `src/agent/policy.py`
  - Parses model tags and validates/normalizes action selection.
- `src/agent/session_state.py`
  - Scene memory, history compaction, strategy memory slots.
- `src/agent/tool_registry.py`
  - Tool definitions and canonical naming.
- `src/agent/llm_client.py`
  - Provider abstraction and model routing.
- `src/agent/schemas.py`, `src/agent/tracing.py`
  - Trace schema and trace persistence helpers.

### Knowledge and Data
- `src/reference/knowledge_base.py`
  - Loads processed data and performs entity lookup.
- `data/processed/*.json`
  - Domain data source for enrichment.

### Evaluation
- `src/eval/replay.py`
  - Offline metrics (validity, latency, token usage, outcomes).

## Integration Points

### External Boundary
- CommunicationMod <-> `src/main.py` via `stdin/stdout` command protocol.

### Internal HTTP/WS Surface (`src/ui/dashboard.py`)
- `POST /update_state`
- `GET /poll_instruction`
- `POST /submit_action`
- `POST /api/ai/mode`
- `POST /api/ai/approve`
- `POST /api/ai/reject`
- `POST /api/ai/status`
- `POST /agent_trace`
- `POST /action_taken`
- `POST /log`
- `GET /api/ai/state`
- `GET /api/runs`
- `GET /api/runs/{run_name}`
- `WS /ws`

## Current Architecture Risks
- Orchestrator concentration in `src/main.py` (many responsibilities in one module).
- Process-local mutable state in `src/ui/dashboard.py` (no durability, weak multi-worker behavior).
- String-heavy action protocol across layers.
- Large template files with embedded scripts/styles.
- Broad exception swallowing in network/UI update paths.
