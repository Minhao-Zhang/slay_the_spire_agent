# Feature Catalog

## Purpose
Record all user-visible and system-critical functionality with trigger, processing path, outputs, and failure/fallback behavior.

## F1: Live State Dashboard
- Trigger/Input: `POST /update_state` from `src/main.py`.
- Processing Path: `src/ui/dashboard.py` -> `process_state(...)` -> `WS /ws` broadcast.
- Outputs/Side Effects: UI receives VM + state id and re-renders.
- Failure/Fallback: endpoint returns error payload; gameplay can continue without dashboard.

## F2: Manual Command Submission
- Trigger/Input: `POST /submit_action` from UI/manual operator.
- Processing Path: `manual_actions_queue` in `src/ui/dashboard.py` -> `GET /poll_instruction` by `src/main.py`.
- Outputs/Side Effects: `src/main.py` executes `print(action)` and posts `/action_taken`.
- Failure/Fallback: blank action ignored; if dashboard unavailable, no manual override available.

## F3: AI Runtime Modes
- Trigger/Input: `POST /api/ai/mode`.
- Processing Path: `ai_runtime["mode"]` in dashboard; `src/main.py` pulls current mode via poll response.
- Outputs/Side Effects:
  - `manual`: no AI execution.
  - `propose`: AI suggests action and waits for approval.
  - `auto`: valid AI suggestion executes automatically.
- Failure/Fallback: invalid mode rejected; if AI unavailable, main forces `manual`.

## F4: AI Proposal and Approval Loop
- Trigger/Input: ready-for-command state with legal actions.
- Processing Path: `src/main.py` -> proposal worker -> `src/agent/graph.py` -> `src/agent/policy.py` -> trace cached in `trace_cache`.
- Outputs/Side Effects: live trace events, final decision, optional sequence queue.
- Failure/Fallback:
  - proposal timeout/crash increments failure streak.
  - AI disabled after configured streak limit.
  - stale proposals discarded on state advance.

## F5: Auto Short-Circuits
- Trigger/Input:
  - exactly one legal action.
  - only `CONFIRM/CANCEL` non-system options.
  - combat reward has guaranteed gold reward.
- Processing Path: `src/main.py` short-circuit checks.
- Outputs/Side Effects: action decided without LLM call.
- Failure/Fallback: if no safe command, fall back to `state` request while ready.

## F6: Token-Based PLAY Resolution
- Trigger/Input: model emits `PLAY <card_uuid_token> [target]`.
- Processing Path: `src/agent/policy.py::resolve_token_play(...)` against current legal actions.
- Outputs/Side Effects: canonical command (`PLAY <hand_index> [monster_index]`).
- Failure/Fallback: invalid resolution returns validation error.

## F7: Tool-Assisted Inspection
- Trigger/Input: model `tool_request` tag.
- Processing Path: tool call loop in `src/agent/graph.py` using `src/agent/tool_registry.py`.
- Outputs/Side Effects: draw/discard/exhaust/deck summary context returned to model.
- Failure/Fallback: unknown/invalid tool request ignored or validated out.

## F8: Replay Viewer
- Trigger/Input: `GET /api/runs`, `GET /api/runs/{run_name}`.
- Processing Path: `src/ui/dashboard.py` loads run logs and reprocesses each state with `process_state`.
- Outputs/Side Effects: UI can step historical snapshots.
- Failure/Fallback: missing run returns error payload.

## F9: Replay Analytics CLI
- Trigger/Input: `python -m src.eval.replay --logs-dir ... [--run ...]`.
- Processing Path: iterate state logs and `.ai.json` sidecars.
- Outputs/Side Effects: JSON metrics report (legality, latency, usage, outcomes).
- Failure/Fallback: malformed JSON skipped.

## F10: Knowledge Enrichment
- Trigger/Input: entity details requested during VM projection.
- Processing Path: `src/ui/state_processor.py` -> `src/reference/knowledge_base.py`.
- Outputs/Side Effects: enriched `kb` subobjects in VM.
- Failure/Fallback: missing lookup yields `kb: null`.
