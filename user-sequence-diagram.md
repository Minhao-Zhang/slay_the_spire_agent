# User sequence diagram

Typical interactions among the operator UI, dashboard, bridge, and game. Modes `manual`, `propose`, and `auto` control how `GET /poll_instruction` returns `manual_actions_queue` entries vs `approved_action` vs bridge-side auto-finalization. Narrative and route tables: [ARCHITECTURE.md](ARCHITECTURE.md).

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant UI as React UI\n(apps/web)
  participant API as Dashboard\n(FastAPI)
  participant WS as WebSocket\n/ws
  participant Br as Bridge\n(src/main.py)
  participant CM as CommunicationMod\n+ game

  Note over Br,API: Bridge startup
  Br->>API: POST /api/ai/status (initial LLM probe)
  API->>WS: snapshot

  Op->>UI: Open monitor or metrics
  UI->>API: WebSocket /ws (initial snapshot on connect)
  UI->>API: GET /api/debug/snapshot (monitor bootstrap)
  opt Run metrics page
    UI->>API: GET /api/runs, GET /api/runs/{run}/metrics, …
  end
  API->>WS: snapshot payload (ai_runtime, VM, trace)
  WS-->>UI: type snapshot

  Note over CM,Br: Live play
  CM->>Br: JSON line (stdin)
  Br->>Br: process_state(state) for logging / shortcuts
  Br->>API: POST /update_state { state, meta }
  API->>API: process_state(envelope) → VM, broadcast
  API->>WS: snapshot
  WS-->>UI: live state + trace slot

  Op->>UI: Set mode (manual / propose / auto)
  UI->>API: POST /api/ai/mode
  API->>WS: snapshot

  Note over Br,API: Background propose + trace streaming
  Br->>API: POST /api/ai/proposal_state (in_flight on/off)
  Br->>API: POST /agent_trace (progress / final / failure)
  API->>WS: snapshot

  alt Propose mode (HITL)
    Op->>UI: Approve, reject, edit, or Retry AI
    UI->>API: POST /api/agent/resume (kind approve | reject | edit)
    UI->>API: POST /api/agent/retry (Retry AI; bridge consumes GET /api/ai/retry_poll)
    Note right of API: POST /api/ai/approve and /api/ai/reject are direct equivalents
    API->>API: approved_action or retry_proposal_request
    API->>WS: snapshot
  else Manual command
    Op->>UI: Enter legal command
    UI->>API: POST /api/debug/manual_command
    API->>API: queue in manual_actions_queue
  else Auto mode
    Note over Br: Bridge finalizes proposal without UI approve when eligible (finalize_ai_execution)
  end

  loop Game waiting for input
    Br->>API: GET /poll_instruction
    API-->>Br: manual_action, approved_action, agent_mode, …
  end

  Br->>CM: print command (stdout)
  Br->>API: POST /action_taken (telemetry)
  API->>WS: optional live updates
```
