# Contracts and Data Models

## Purpose
Capture runtime contracts to remove ambiguity during rewrite and identify implicit string-based semantics that must become typed.

## C1: Game Adapter Input Contract
- Source: CommunicationMod JSON to `src/main.py`.
- Required behavioral fields:
  - `in_game: bool`
  - `ready_for_command: bool`
  - `available_commands: list[str]`
  - `game_state: object` (screen, combat, map, deck, relics, potions)
- Rewrite rule: define strict adapter DTOs with versioning and validation at ingestion.

## C1b: Runtime State Identity Contract
- Current behavior: `state_id` is a deterministic hash of normalized ingress payload content.
- Implication: `state_id` is stable for identical payloads but not monotonic by time.
- Rewrite rule: preserve deterministic identity semantics for parity, and do not assume numeric/time ordering in stale checks.

## C1c: State Hash Canonicalization Contract
- `state_id` must be produced from a canonical JSON representation with:
  - stable key ordering,
  - normalized numeric formats,
  - normalized boolean/null handling,
  - deterministic list ordering only where list semantics are unordered.
- Exclude transport-only/ephemeral fields from hash input (for example receive timestamp, ingestion sequence id, transient UI-only annotations).
- Include all command-relevant gameplay fields that affect legality or intent resolution.
- Publish canonicalization test fixtures:
  - equivalent payload variants that must hash equal,
  - semantically distinct payload variants that must hash different.
- Hash algorithm and canonicalization version must be explicit (`state_id_version`) for migration safety.

## C2: View Model Contract (`process_state`)
- Target consumers: dashboard UI + agent prompt pipeline.
- VM top-level shape:
  - `in_game`, `header`, `actions`, `combat`, `screen`, `inventory`, `map`, `sidebar`, `last_action`
- `actions` entries (current shape):
  - `label`, `command`, `style`
  - optional `card_uuid_token`, `hand_index`, `monster_index`
- Rewrite rule: formal `ViewModel` schema and `ActionCandidate` schema with explicit discriminated unions by action kind.

## C3: Decision Contract (`FinalDecision`)
- Current schema from `src/agent/schemas.py`:
  - `chosen_commands: list[str]`
  - `chosen_command: str` (backward compatibility alias)
  - `chosen_label: str`
  - `action_type: str`
  - `choice_index: int | null`
  - `target_name: str`
- Rewrite rule: remove ambiguous dual fields (`chosen_commands` vs `chosen_command`) and enforce one canonical representation.
- LangChain planning rule: bind `DecisionProposal` to a strict Pydantic schema and enforce structured response parsing at the gateway boundary.

## C4: Validation Contract
- Current resolution order in `src/agent/policy.py`:
  1. Token PLAY resolution.
  2. Exact command normalization match.
  3. Label match.
  4. `action_type=choose` + `choice_index`.
- Rewrite rule: explicitly separate intent resolution from command emission and record confidence + reason code.

## C5: Trace and Telemetry Contract
- Live trace type: `AgentTrace` in `src/agent/schemas.py`.
- Persisted sidecar type: `PersistedAiLog`.
- Includes: identity, status, prompts, parsed proposal, validation, decision, tool names, latency, token usage, planner metadata, model metadata.
- Rewrite rule: define event schema registry and version each event.
- LangGraph planning rule: persist checkpoint metadata (`thread_id`, checkpoint id, parent checkpoint id) with trace events for replay and debug.
- Add event idempotency key contract to support at-least-once append and reconciliation.

## C6: Interrupt and Resume Contract
- Human approval is a first-class contract, not ad-hoc polling state.
- Required fields:
  - `interrupt_id`
  - `state_id`
  - `proposal_id`
  - `requested_action`
  - `allowed_response_types` (`accept`, `edit`, `reject`, `feedback`)
- Resume payload must be typed and validated before continuing graph execution.
- Operator identity and reason metadata are required for mutating resume actions in non-local deployments.

## C7: Graph State Update Contract
- Define one canonical `AgentRuntimeState` type for the graph runtime.
- Node return payloads are patch/delta objects, not full state replacements.
- Each state section has one owning node (or tightly bounded owner set).
- Reducers must be defined for any field that may receive concurrent updates.
- Full-state recreation inside node logic is explicitly prohibited.

## C8: Strategic Planner Collaboration Contract
- Strategic planner is advisory and must not output directly executable commands.
- Required `StrategicPlan` fields:
  - `plan_id`
  - `state_id`
  - `turn_key`
  - `trigger_reason` (`combat_start` | `long_term_impact`)
  - `horizon`
  - `primary_intent`
  - `recommended_lines`
  - `avoid_list`
  - `risk_flags`
  - `expires_at` or equivalent deterministic invalidation metadata
- Tactical decision records alignment with strategic guidance:
  - `followed`
  - `partially_followed`
  - `diverged` (+ required reason code)
- Planner failure behavior must degrade safely to tactical-only flow with explicit telemetry.

## Command Grammar (Current)
- Commands are free-form strings such as:
  - `PLAY 1`
  - `PLAY 1 0`
  - `PLAY a1b2c3 0`
  - `choose 0`, `choose boss`, `choose purge`
  - `POTION USE 0 1`, `POTION DISCARD 0`
  - `END`, `CONFIRM`, `PROCEED`, `RETURN`, `WAIT 10`, `state`
- Rewrite rule: model as typed command AST with serializer per game protocol.

## Command Fallback Contract (Current)
- When no explicit manual/approved/AI command is selected:
  - If `wait` is available, emit `WAIT 10` (idle heartbeat).
  - Else if `state` is available, emit `state` (refresh request).
  - Else emit nothing and wait for next ingress update.
- Last-resort safety behavior:
  - If game is `ready_for_command` and no command is available after full resolution, emit `state` to avoid command-deadlock.

## Stringly-Typed Risks to Eliminate
- Screen and status literals (`"MAP"`, `"stale"`, `"awaiting_approval"`).
- Action command parsing using string normalization.
- Implicit behavior from command prefixes (`startswith("PLAY ")`).
- Mixed case/spacing normalization as logic.
- Endpoint payload dicts with optional keys and no version.

## Must-Type List for Rewrite
1. Game ingress payloads.
2. View model and legal actions.
3. Decision output payload.
4. Command AST and serializer.
5. Trace events and status transitions.
6. Control API request/response DTOs.
7. Interrupt/resume payloads for human-in-the-loop gates.
8. Checkpoint identity fields used by replay/time-travel workflows.
9. Canonical graph state and node delta update schemas.
