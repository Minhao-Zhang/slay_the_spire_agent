# Architecture

## Current Runtime Data Flow

```mermaid
flowchart LR
    game[CommunicationModOrGame] -->|"raw state JSON (stdin)"| main[src/main.py]

    subgraph vmLayer [VMAndControlSync]
        main -->|"process_state(raw)"| stateProc[src/ui/state_processor.py]
        stateProc -->|"vm + legal actions + KB enrichment"| main
        main -->|"POST /update_state (state + state_id)"| dashboard[src/ui/dashboard.py]
        dashboard -->|"broadcast state + trace + logs"| ui[index.html + ai_debugger.html]
        ui -->|"manual/approve/reject/mode"| dashboard
        dashboard -->|"GET /poll_instruction"| main
    end

    subgraph decisionLayer [AgentDecisionLayer]
        main -->|"start_proposal(vm,state_id,mode)"| graph[src/agent/graph.py]
        graph -->|"build prompt sections"| prompt[src/agent/prompt_builder.py]
        graph -->|"scene memory + compaction + strategy slots"| session[src/agent/session_state.py]
        graph -->|"optional planner node (LLM_ENABLE_PLANNER)"| planner[plan_turn]
        prompt -->|"system prompt + user prompt"| llm[src/agent/llm_client.py]
        llm -->|"stream deltas + tool calls"| graph
        graph -->|"execute registered tool"| tools[src/agent/tool_registry.py]
        tools -->|"tool outputs"| graph
        graph -->|"parse + resolve intent to legal command"| policy[src/agent/policy.py]
        graph -->|"live trace updates"| trace[src/agent/tracing.py + schemas.py]
        trace -->|"POST /agent_trace"| dashboard
    end

    subgraph persistence [PersistenceAndEval]
        main -->|"write state logs"| logs[logs/<run>/<event>.json]
        trace -->|"write sidecar logs"| ailogs[logs/<run>/<event>.ai.json]
        ailogs -->|"offline metrics"| replay[src/eval/replay.py]
    end

    main -->|"only execution boundary: print(action)"| game
```

## Decision Loop Details

1. `src/main.py` reads raw JSON state, computes deterministic `state_id`, builds VM with `process_state()`.
2. `src/main.py` sends state to dashboard and polls instruction channel (`manual_action`, `approved_action`, `agent_mode`).
3. If eligible, it starts one background proposal (`ThreadPoolExecutor`, single worker).
4. `src/agent/graph.py` runs:
   - `build_prompt` (session scene key, compaction, strategy memory update),
   - optional `plan_turn` (feature-flagged),
   - `run_agent` (streaming LLM call),
   - `run_tool` loop (bounded by `max_tool_roundtrips`),
   - `validate_decision`.
5. `src/agent/policy.py` validates decision with command normalization and intent fallbacks (`chosen_label`, `action_type`, `choice_index`).
6. Final action is executed only by `print(action)` in `src/main.py` (manual/propose/auto policy applied there).

## Control Plane and Execution Modes

- `manual`: only operator/manual actions execute.
- `propose`: AI proposes, human approves/edits/rejects in dashboard.
- `auto`: AI proposal auto-executes when valid.
- Dashboard is control-plane only; it never emits game commands directly.

## Tooling Path (Current)

Tools are centralized in `src/agent/tool_registry.py` and exposed by `src/agent/llm_client.py`:

- `inspect_draw_pile`
- `inspect_discard_pile`
- `inspect_exhaust_pile`
- `inspect_deck_summary`

`graph.py` executes tools via the registry and feeds `function_call_output` back to the model for continuation.

## Prompt and Memory Inputs

`src/agent/prompt_builder.py` composes sections including:

- `PLAYER STATE`, `LEGAL ACTIONS`, `VALID PLAYS`,
- `MONSTERS`, `HAND`, `PLAYER POWERS`, `RELICS`, `POTIONS`,
- `MAP PLANNING`, `MAP SCENE` (when applicable),
- `CURRENT SCREEN`, `RECENT EXECUTED ACTIONS`,
- `STRATEGY MEMORY` (structured slots),
- `TOOLING NOTES`.

Memory behavior in `src/agent/session_state.py`:

- Global chat history across the run.
- Scene-scoped recent executed actions.
- Compaction into `## COMPACTED HISTORY` when token threshold is exceeded.
- Structured strategy memory slots (`deck_plan`, `pathing_goal`, `boss_prep`, `constraints`).

## Reliability and Fallback

`src/main.py` tracks proposal failure streaks:

- Transient proposal failure does not immediately disable AI.
- AI is disabled for run only after `LLM_PROPOSAL_FAILURE_STREAK_LIMIT`.
- On success, streak resets and normal operation resumes.

## Trace and Log Schema (Current)

Live `AgentTrace` includes:

- decision/state identity (`decision_id`, `state_id`, `turn_key`),
- planning/prompt/response fields,
- parsed proposal + validation,
- tool names used,
- planner summary,
- token usage + latency,
- execution outcome and approval status.

Persisted sidecar log (`*.ai.json`) includes matching diagnostic fields to support replay evaluation in `src/eval/replay.py`.
