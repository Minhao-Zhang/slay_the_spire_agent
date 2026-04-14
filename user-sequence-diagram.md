# User sequence diagram

Typical interactions among the operator UI, dashboard, bridge, and game. Modes `manual`, `propose`, and `auto` are reflected in how `GET /poll_instruction` receives `manual_actions_queue` entries vs `approved_action` vs bridge-side auto-finalization. Narrative and tables: [architecture.md](architecture.md).

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant UI as React UI\n(apps/web)
  participant API as Dashboard\n(FastAPI)
  participant WS as WebSocket\n/ws
  participant Br as Bridge\n(src/main.py)
  participant CM as CommunicationMod\n+ game

  Op->>UI: Open monitor / metrics
  UI->>API: Connect WS, GET /api/debug/snapshot (as needed)
  API->>WS: snapshot payload (ai_runtime, VM, trace)
  WS-->>UI: type snapshot

  Note over CM,Br: Live play
  CM->>Br: JSON line (stdin)
  Br->>API: POST /update_state
  API->>API: process_state → VM, broadcast
  API->>WS: snapshot
  WS-->>UI: live state + trace slot

  Op->>UI: Set mode (manual / propose / auto)
  UI->>API: POST /api/ai/mode
  API->>WS: snapshot

  Note over Br,API: Bridge may start SpireDecisionAgent.propose in background; traces stream via POST /agent_trace
  Br->>API: POST /agent_trace (progress / final)
  API->>WS: snapshot

  alt Propose mode (HITL)
    Op->>UI: Approve, reject, edit, or Retry AI
    UI->>API: POST /api/ai/approve | /reject | /api/agent/retry …
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
