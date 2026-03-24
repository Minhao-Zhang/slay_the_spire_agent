# Current System Baseline

## Runtime Flow (Legacy)
1. `src/main.py` receives game state from CommunicationMod stdin.
2. `src/ui/state_processor.py` builds VM and legal actions.
3. `src/main.py` sends updates to `src/ui/dashboard.py`.
4. `src/agent/graph.py` runs LLM/tool loop and decision parsing.
5. `src/main.py` emits final command to game process.
6. Raw states + AI sidecars are persisted under `logs/`.

## Main Components
- `src/main.py`: orchestration, mode policy, queueing, retries, execution.
- `src/ui/dashboard.py`: control plane API + websocket + in-memory runtime state.
- `src/agent/*`: prompting, provider calls, parsing, policy resolution, tracing.
- `src/eval/replay.py`: offline replay analytics.

## Current User-Facing Features
- Live dashboard state updates.
- Manual command queue submission.
- AI runtime modes (`manual`, `propose`, `auto`).
- Approval loop with edit/reject support.
- Auto short-circuits for known safe cases.
- Replay viewer and replay analytics CLI.
- Knowledge enrichment for cards/relics/monsters/events.

## Current Logging Model
- Raw game states: run-local JSON files.
- AI traces: sidecar log files and in-memory trace cache.
- Transport: live state + trace updates over websocket.

## Known Pain Points
- God-module orchestration in `src/main.py`.
- Process-local mutable state in dashboard (`ai_runtime`, manual queue).
- Stringly-typed actions and statuses.
- Monolithic template assets with embedded JS/CSS.
- Weak concurrency/durability for multi-worker scenarios.

## Baseline Parity Behaviors To Preserve
- Command precedence and fallbacks (`WAIT 10` / `state` safety behavior).
- Proposal staleness handling via deterministic `state_id`.
- Sequence queue semantics and invalidation.
- Approval lifecycle semantics (`awaiting`, `approved`, `edited`, `rejected`, `stale`).
- Replay metrics and legality checks.
