# Architecture

This document describes how **Spire Agent** is structured end to end: the game bridge, the FastAPI dashboard that hosts the agent, the LangGraph decision pipeline, durable knowledge and memory, reflection, and the React operator UI. Paths are relative to the repository root unless noted.

---

## 1. System overview

At the highest level, three cooperating processes are usual in development: the **dashboard** (Python + agent), the **bridge** (Python stdin/stdout to CommunicationMod), and optionally the **Vite** dev server for the SPA. The game mod pushes JSON state to the bridge; the bridge forwards it to the dashboard; the dashboard runs the agent when asked and exposes HTTP/WebSocket for the UI.

```mermaid
flowchart TB
  subgraph Game["Game + mod"]
    STS["Slay the Spire"]
    CM["CommunicationMod"]
    STS <--> CM
  end

  subgraph Processes["Typical dev processes"]
    Bridge["Bridge\nsrc/main.py"]
    API["Dashboard + agent\nuvicorn src.ui.dashboard:app"]
    UI["Operator UI\napps/web Vite → :5173"]
  end

  subgraph Data["On disk"]
    Know["data/knowledge/\nstrategy markdown"]
    Ref["data/reference/\nJSON facts"]
    Mem["MEMORY_DIR\nlessons · index"]
    Logs["logs/games/\nper-run frames"]
  end

  subgraph Async["After a run (bridge thread)"]
    Refl["Reflection pipeline"]
    Cons["Consolidation\n(every N runs)"]
  end

  CM <-->|stdin/stdout JSON lines| Bridge
  Bridge <-->|HTTP :8000| API
  UI <-->|proxy /api /ws| API
  API --> Know
  API --> Ref
  API --> Mem
  Bridge --> Logs
  API -.->|run metrics APIs| Logs
  Bridge -.-> Refl
  Logs -.-> Refl
  Refl --> Mem
  Bridge -.-> Cons
  Cons --> Mem
```

**Ingress path:** each game state line is handled by [`src/main.py`](src/main.py), which `POST`s to [`/update_state`](src/ui/dashboard.py); the dashboard uses [`src/ui/state_processor.py`](src/ui/state_processor.py) to build the **view model** consumed by the agent and UI.

**Egress path:** when the mod is ready for input, the bridge `GET`s [`/poll_instruction`](src/ui/dashboard.py), receives a manual or AI-approved command, validates it against the current legal list, and **prints** the line for the mod.

---

## 2. Dashboard HTTP and WebSocket surface

The dashboard is the single long-lived Python service that owns **`SpireDecisionAgent`**, session state, and broadcasting snapshots to browsers.

| Cluster | Role | Representative routes |
|--------|------|-------------------------|
| Bridge | Game loop integration | `POST /update_state`, `GET /poll_instruction`, `POST /action_taken`, `POST /log`, `POST /agent_trace` |
| AI / HITL | Modes, approval, retries | `POST /api/ai/approve`, `POST /api/ai/reject`, `POST /api/ai/mode`, `POST /api/ai/auto_start`, `GET /api/ai/state`, `GET /api/ai/retry_poll`, `POST /api/agent/retry`, `GET /api/agent/status`, `POST /api/agent/resume` |
| Debug / live | Snapshot + manual play | `GET /api/debug/snapshot`, `POST /api/debug/ingress`, `POST /api/debug/manual_command`, `GET /api/debug/poll_instruction`, **`WebSocket /ws`** (`snapshot` events) |
| Runs / metrics | Log-backed analytics | `GET /api/runs`, `GET /api/runs/{run_name}/metrics`, `GET /api/runs/{run_name}/map_history`, `GET /api/runs/{run_name}/frames`, … |
| History (stub) | Placeholder | `GET /api/history/*` — not backed by persistent thread storage yet |

Implementation: [`src/ui/dashboard.py`](src/ui/dashboard.py). The React app expects a **`DebugSnapshotPayload`**-shaped snapshot (AI runtime, latest trace, ingress metadata); see [`src/agent/schemas.py`](src/agent/schemas.py) for trace types.

---

## 3. LangGraph decision pipeline (detailed)

The in-process agent is [`SpireDecisionAgent`](src/agent/graph.py). It compiles a **`StateGraph`** over **`GraphState`**: view model (`vm`), prompts, messages, tool round-trips, **`AgentTrace`**, memory hits, strategist output, and planning blocks.

```mermaid
flowchart LR
  START([START]) --> S[run_strategist]
  S --> P[resolve_combat_plan]
  P --> A[assemble_prompt]
  A --> R[run_agent]
  R -->|tool calls| T[run_tool]
  T --> R
  R -->|final or error| V[validate_decision]
  R -->|disabled / early end| END([END])
  V --> END
```

**Node responsibilities**

| Node | Module glue | What it does |
|------|-------------|----------------|
| **`run_strategist`** | [`strategist.py`](src/agent/strategist.py), [`memory/store.py`](src/agent/memory/store.py), [`memory/context_tags.py`](src/agent/memory/context_tags.py) | On a new “scene”, builds tags, retrieves a large pool of procedural hits from `MemoryStore`, loads a compact **knowledge index** from markdown under `KNOWLEDGE_DIR`, and (if AI is on) calls the **support** model to pick final lesson hits and emit `planning_context_block` / `non_combat_plan_block`. Caches hits for the same scene. |
| **`resolve_combat_plan`** | [`planning.py`](src/agent/planning.py) | Combat-only: produces combat planner summary / guide for turn 1+ as configured; does not overwrite strategist-owned non-combat plan text. |
| **`assemble_prompt`** | [`prompt_builder.py`](src/agent/prompt_builder.py), [`session_state.py`](src/agent/session_state.py), [`llm_client.py`](src/agent/llm_client.py) | Sets scene on the session; may **compact** older chat via the support model when over token threshold; builds the user prompt from VM, action history, strategy notes, combat guide, **memory hits**; prepends strategist/planning blocks; appends user message to `TurnConversation`. |
| **`run_agent`** | [`llm_client.py`](src/agent/llm_client.py), [`tool_registry.py`](src/agent/tool_registry.py) | Calls the **decision** model with tools (effort from config); records LLM segments on the trace. |
| **`run_tool`** | [`tool_registry.py`](src/agent/tool_registry.py) | Executes tool calls; increments round-trip counter; loops back to **`run_agent`**. |
| **`validate_decision`** | [`policy.py`](src/agent/policy.py) | Parses model output, validates the chosen command against policy and legality, finalizes trace status. |

**Prompt construction:** [`build_user_prompt`](src/agent/prompt_builder.py) incorporates the processed VM; it can attach **map path analysis** via [`map_analysis.analyze_map_paths`](src/agent/map_analysis.py) when the screen supplies map data. Reference card text can be enriched from [`src/reference/knowledge_base.py`](src/reference/knowledge_base.py) (`data/reference/*.json`).

**System prompt:** loaded from [`src/agent/prompts/system_prompt.md`](src/agent/prompts/system_prompt.md) through [`config.load_system_prompt`](src/agent/config.py).

---

## 4. Agent package map (file-level)

```mermaid
flowchart TB
  subgraph Entry["Integration"]
    G[graph.py\nSpireDecisionAgent · StateGraph]
    CFG[config.py\nAgentConfig · env]
    SCH[schemas.py\nAgentTrace · modes]
  end

  subgraph LLM["Models"]
    LLMCL[llm_client.py\nOpenAI-compatible · dual models]
  end

  subgraph Context["Context & prompts"]
    PB[prompt_builder.py]
    PL[planning.py]
    ST[strategist.py]
    MA[map_analysis.py]
    VM[vm_shapes.py]
  end

  subgraph Memory["Memory & knowledge"]
    MS[memory/store.py\nretrieve · procedural index]
    MT[memory/types.py · strategy_docs · tags · tag_utils]
  end

  subgraph Tools["Tools & policy"]
    TR[tool_registry.py]
    POL[policy.py]
  end

  subgraph Session["Session"]
    SS[session_state.py\nTurnConversation · history · notes]
  end

  subgraph Trace["Observability"]
    TRA[tracing.py]
  end

  subgraph Reflect["Post-run"]
    RUN[reflection/runner.py]
    ANA[reflection/analyzer.py]
    REF[reflection/reflector.py]
    PER[reflection/memory_storage.py]
    CON[reflection/consolidator.py]
  end

  G --> LLMCL
  G --> ST
  G --> PL
  G --> PB
  G --> TR
  G --> POL
  G --> MS
  G --> SS
  G --> TRA
  PB --> MA
  ST --> MS
  RUN --> ANA
  RUN --> REF
  RUN --> PER
  CON --> MS
```

**Bridge-only / eval:** [`src/main.py`](src/main.py) orchestrates proposal futures, queueing multi-command sequences, `finalize_ai_execution`, and schedules **`run_reflection_pipeline`** plus periodic **`consolidate_procedural_memory`** after runs. [`src/eval/replay.py`](src/eval/replay.py) can replay logged frames without the game.

---

## 5. Reflection and consolidation (detailed)

When a run directory under `logs/games/` is finalized, the bridge may start a background job that:

1. **`RunAnalyzer.analyze(game_dir)`** — builds a structured run report ([`reflection/analyzer.py`](src/agent/reflection/analyzer.py)).
2. **`reflect_on_run`** — decision model proposes procedural lessons and episodic summary ([`reflection/reflector.py`](src/agent/reflector.py)).
3. **`persist_reflection_to_memory`** — writes into `MemoryStore` ([`reflection/memory_storage.py`](src/agent/reflection/memory_storage.py)); lesson outcomes can be updated from victory/defeat.
4. Writes **`reflection_output.json`** beside the run for debugging.

Separately, **`consolidate_procedural_memory`** ([`reflection/consolidator.py`](src/agent/reflection/consolidator.py)) runs every **`CONSOLIDATION_EVERY_N_RUNS`** (see [`main._schedule_post_run_consolidation`](src/main.py)) to archive or merge low-confidence procedural entries without an LLM.

```mermaid
sequenceDiagram
  participant B as Bridge main.py
  participant L as logs/games/run_dir
  participant R as reflection/runner
  participant A as RunAnalyzer
  participant F as Reflector LLM
  participant M as MemoryStore

  B->>L: run complete
  B->>R: run_reflection_pipeline
  R->>A: analyze
  A->>L: read frames
  R->>F: reflect_on_run
  F-->>R: lessons + episodic
  R->>M: persist_reflection_to_memory
  B->>M: consolidate (every N runs)
```

---

## 6. Frontend (`apps/web`)

Vite + React Router: monitor (`/`), run metrics (`/metrics`), multi-run compare (`/metrics/compare`), map replay (`/metrics/map`). Dev server proxies **`/api`** and **`/ws`** to **`127.0.0.1:8000`**. See [`apps/web/README.md`](apps/web/README.md) and route table in [`apps/web/src/App.tsx`](apps/web/src/App.tsx).

---

## 7. Data directories (conceptual)

| Location | Consumed by | Purpose |
|----------|-------------|---------|
| `data/knowledge/**` | `MemoryStore` index + strategist index | Human-authored strategy markdown for retrieval |
| `data/reference/*.json` | `knowledge_base.DataStore`, tools, prompts | Spreadsheet-derived facts (cards, relics, …) |
| `MEMORY_DIR` (default `data/memory`) | `MemoryStore` | Procedural/episodic lessons, consolidation counter |
| `logs/games/<run>/` | Bridge writes; metrics UI + reflection reads | `*.json` frames, optional `*.ai.json`, reports |

---

## Legacy diagram: ingress only

Minimal view of who talks to whom on the wire:

```mermaid
flowchart LR
  Game[CommunicationMod]
  Main[src.main]
  Dash[src.ui.dashboard]
  React[apps/web Vite]

  Game -->|stdin JSON| Main
  Main -->|POST /update_state| Dash
  Main -->|GET /poll_instruction| Dash
  React -->|/api/debug/* /ws| Dash
```

- **Game → bridge:** each line includes `meta.state_id` and is normalized through [`process_state`](src/ui/state_processor.py).
- **Operators:** WebSocket **`/ws`** broadcasts **`snapshot`** payloads so the monitor stays live without polling everything.
