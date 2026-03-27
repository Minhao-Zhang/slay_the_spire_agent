# Legacy archive vs greenfield — behavioral parity notes

This document compares **archive** code under `archive/legacy_src/` (especially `src/main.py` and the legacy agent stack) with the **greenfield** CommunicationMod + `control_api` + LangGraph path (`src/main.py`, `src/decision_engine/`, `src/domain/`).

- **§§1–4** — short-circuits, hashing, card tokens, multi-command queues (original scope).
- **§5–6** — other legacy-only behavior and a compact table.
- **§7** — **extended inventory** of additional legacy capabilities not covered above.
- **§8** — **implementation candidates** (backlog-style; not a committed roadmap).

Use this when deciding whether to port behavior, document intentional cuts, or scope new work.

---

## 1. Main-loop short-circuits (legacy) vs greenfield

### Legacy (`archive/legacy_src/src/main.py`)

When `ready_for_command` is true, the legacy loop can **avoid starting an LLM proposal** in several situations:

- **Single non-system action**: if the projected action list collapses to one meaningful operator command, legacy may execute it immediately (no graph/LLM round).
- **Auto-confirm**: when the only meaningful commands are `CONFIRM` and optionally `CANCEL`, legacy chooses `CONFIRM` without an LLM call (e.g. hand-select / discard flows).
- **Combat reward gold**: `choose_combat_reward_gold_command` auto-picks a `choose <idx>` command for GOLD rewards when it matches a legal action (still inside the same “bypass proposal” family of behavior).
- **Manual poll** and **idle** (`wait` / `state`) behave similarly at a high level to greenfield.

These are **policy shortcuts in the game-process loop**, not deduplication of HTTP ingress.

### Greenfield (`src/main.py` + `src/control_api/` + LangGraph)

- The mod **always POSTs ingress** when the normalized game state changes; duplicate suppression is **only** “same `state_id` as last push” (`_push_ingress_unless_duplicate` using `compute_state_id`), not “skip LLM because only one legal action.”
- **Whether** the LangGraph run does heavy work depends on **control API / graph mode** (`manual` / `auto` / `propose`) and HITL, not on legacy-style **CONFIRM-only** or **single-action** branches in the mod.
- There is **no** port of `choose_combat_reward_gold_command` in the greenfield mod loop.
- Debug ingress can optionally bypass an API-level unchanged-state short-circuit (see comments in `src/control_api/app.py` around `/api/debug/ingress`).

**Gap summary:** legacy **in-loop LLM / proposal skips** (single action, CONFIRM/CANCEL set, gold reward auto-pick) are **not** replicated in greenfield’s CommunicationMod the same way; greenfield relies on graph configuration and simpler idle/manual paths instead.

---

## 2. Hashing and state identity

### Legacy (`archive/legacy_src/src/agent/tracing.py`)

- **`build_state_id(state: dict)`** — SHA-256 over **canonical JSON of the entire raw state dict** (first 16 hex chars). Very sensitive to any extra or noisy fields in the payload.
- **`combat_encounter_fingerprint(vm)`** — stable id for “this fight” from floor + live monsters (name + max_hp); used for strategic / session continuity concepts in the legacy stack.
- **`build_turn_key(vm)`** — scene key: per-combat (`COMBAT:<floor>`) or `<screen_type>:<floor>` out of combat; used in traces and prompt scoping (`AgentTrace`, `PersistedAiLog`).

### Greenfield (`src/domain/contracts/state_id.py`)

- **`compute_state_id(ingress)`** — versioned hash (`v1-…`) over an **explicit subset** of the parsed ingress (`_FINGERPRINT_KEYS`: `in_game`, `ready_for_command`, `available_commands`, `game_state`). Intentionally **not** the full raw line JSON.
- **No** direct equivalent in the agent layer to legacy **`combat_encounter_fingerprint`** or **`build_turn_key`** for traces, memory keys, or planner continuity (telemetry may carry `state_id` and view-model fields instead).

**Gap summary:** both stacks use **content hashes for `state_id`**, but **inputs differ** (full raw dict vs fingerprint keys). Legacy **combat encounter fingerprint** and **turn_key** semantics are **largely absent** from greenfield’s decision path unless reintroduced elsewhere.

---

## 3. Card identity and `card_uuid_token`

### Legacy

- `archive/legacy_src/src/ui/state_processor.py` builds legal actions with a **short token** from card UUID (first 6 chars) for compact labels / token-based plays.
- `archive/legacy_src/src/agent/policy.py` (`resolve_token_play`, etc.) maps those tokens to concrete `play …` commands in multi-step / planner flows.

### Greenfield

- `src/domain/state_projection/legal_actions.py` attaches **`card_uuid_token`** (first 6 of full UUID) to relevant `GameAction` rows, consistent with the legacy slicing approach.
- **End-to-end parity** depends on whether **proposers, validation, and any future token-resolution** match legacy policy behavior (greenfield’s graph currently centers on **one** `emitted_command` per resolution path; see below).

**Gap summary:** the **projection** carries card tokens; **legacy-style multi-token command resolution** in policy may not be fully mirrored if only single-command emission is used.

---

## 4. Multiple commands per suggestion / queued execution

### Legacy (`archive/legacy_src/src/agent/schemas.py`, `main.py`)

- **`FinalDecision.chosen_commands`** — list of commands; **`chosen_command`** is kept in sync as the first element.
- Traces and persisted logs track **`final_decision_sequence`**.
- **`queued_sequence`** in `main.py` holds **remaining** token-based commands after approval; the loop can emit the next command on subsequent `ready_for_command` ticks **without** a new LLM turn, until the sequence is cleared (e.g. turn change, failure).

### Greenfield (`src/decision_engine/graph.py`, telemetry)

- Graph state exposes a single **`emitted_command: str | None`** per resolution; there is **no** first-class **`chosen_commands`** list or **server-side queue** of remaining commands mirrored in the CommunicationMod loop.
- HITL approves one edited or approved command path; **auto** mode can emit one command from mock policy.

**Gap summary:** legacy **multi-command proposals** and **post-approval queues** are **not** present in greenfield at the same abstraction level; reproducing them would require schema + graph + mod loop changes.

---

## 5. Other legacy-only behaviors (brief)

- **Background proposal executor** — legacy starts LLM work in a **thread pool** while the game advances; greenfield runs the graph **synchronously** under `agent_runtime` lock on each ingress (no overlapping proposal while the game advances).
- **Rich trace / AI log sidecars** — legacy writes `.ai.json` next to state logs with planner fields, token usage, etc.; greenfield uses a different trace/telemetry shape (`src/trace_telemetry/`, SQLite history).
- **Proposal failure streak / disable AI for run** — legacy policy in `main.py`; greenfield handles failures inside graph/proposal hygiene (`failure_streak` in graph state) and does not expose the same “disable AI for rest of run” UX from the mod/dashboard.

---

## 7. Extended inventory — more legacy features with weak or no greenfield equivalent

The list below is **not** exhaustive; it reflects a pass over `archive/legacy_src/src/` (agent, UI, eval) vs greenfield `src/`.

### 7.1 LLM I/O format and parsing

| Legacy | Greenfield |
|--------|------------|
| Structured **XML-like tags** in model output: `<reasoning>`, `<tool_request>`, `<final_decision>` with JSON inside; **truncated-stream** handling when `</final_decision>` is missing (`archive/legacy_src/src/agent/policy.py`) | **Single JSON object** response for tactical propose: `command` + `rationale` only (`src/agent_core/pipeline.py`, `parse_proposal_json`) |
| **Tool request** embedded in text, round-trip to `tool_registry` | No tool loop in the tactical graph |
| **OpenAI Responses API** + **Chat Completions**, `previous_response_id` threading, streaming chunks (`archive/legacy_src/src/agent/llm_client.py`) | **Chat-style gateway** only (`src/llm_gateway/openai_chat.py`, `stub.py`); no Responses API / conversation threading in agent_core |

### 7.2 Prompting and model routing

| Legacy | Greenfield |
|--------|------------|
| Large **`prompt_builder`**: buff glossary, PLAY syntax for **tokens**, combat hand lines with `show_token=True`, optional **strategy corpus** (`include_strategy_corpus`, `data/strategy/curated_strategy.md`) | **`state_prompt.build_tactical_state_summary`** KB-enriched, hand lines **can** show `token=` (`src/agent_core/state_prompt.py`), but legal-action list in the user message is still **full command strings** — model is steered toward copying an exact `command` |
| **Per-context model slot**: `combat_turn_llm`, `non_combat_turn_llm`, `combat_plan_llm` (reasoning vs fast) | **Single proposer path**; optional `model_hint` on gateway request, no built-in combat vs map routing |
| **Conversation history** in `TurnConversation`, **compaction** when estimated tokens exceed `history_compact_token_threshold` | **No** multi-turn LLM transcript in agent_core; LangGraph **memory** node stores a short episodic log + one `last_turn` long-term key, not legacy `strategy_memory` |

### 7.3 Combat planner (“strategic” sub-node)

| Legacy | Greenfield |
|--------|------------|
| Optional **`plan_turn`** node before `run_agent` when `planner_enabled`; **`generate_combat_plan`**; plan cached per **`combat_encounter_fingerprint`** in session (`archive/legacy_src/src/agent/graph.py`, `session_state.py`) | **No** combat planning sub-call; specs for longer-horizon planning live in docs (e.g. `13-strategic-planner-collaboration.md`) but are **not** implemented in the tactical graph |

### 7.4 Tool-assisted inspection

| Legacy | Greenfield |
|--------|------------|
| **`inspect_draw_pile`**, **`inspect_discard_pile`**, **`inspect_exhaust_pile`**, **`inspect_deck_summary`** with formatted pile/deck text (`archive/legacy_src/src/agent/tool_registry.py`); `max_tool_roundtrips` | **No** equivalent tools in `src/decision_engine/` or `src/agent_core/` |

### 7.5 Session-scoped strategy memory (legacy)

Legacy `TurnConversation` maintains **`strategy_memory`** slots (`deck_plan`, `pathing_goal`, `boss_prep`, `constraints`) updated from deck/inventory heuristics (`session_state.py`). Greenfield’s **`memory_update_node`** only appends episodic entries and writes **`last_turn`** under namespace `("strategy", class, thread_id)` — not the same structured scratchpad.

### 7.6 Policy: PLAY token resolution

Legacy **`resolve_token_play`** turns `PLAY <6-char-token> [target]` into canonical numeric `PLAY` commands against current legal rows. Greenfield **`resolve_to_legal_command`** matches **exact** or **normalized** full command strings only — it does **not** resolve UUID tokens. (Prompts may still **show** tokens to the human or model, but the resolver will not map them.)

### 7.7 HTTP / WebSocket API shape (legacy dashboard vs control API)

Legacy **`archive/legacy_src/src/ui/dashboard.py`** exposes patterns the CommunicationMod and debugger relied on:

- **`GET /poll_instruction`** returns **`agent_mode`** synced from dashboard **`POST /api/ai/mode`** and **`approved_action`** after **`/api/ai/approve`**.
- **`POST /agent_trace`**, **`POST /action_taken`**, **`POST /log`** for live UI fan-out.
- **`GET /api/runs`**, **`GET /api/runs/{run_name}`** — **directory-based** log replay (reprocess with `process_state`).

Greenfield **`src/control_api/app.py`**:

- **`GET /api/debug/poll_instruction`** returns **`agent_mode": "manual"` always** (actual mode is **`SLAY_AGENT_MODE`** on the server). The greenfield mod only **requires** `manual_action` today, but anything expecting **live mode** or **approved_action** on poll is **not** wire-compatible with legacy.
- Approved paths go through **`POST /api/agent/resume`** and **`queue_manual`** of **`emitted_command`** in `agent_runtime` — different contract.
- History is **`/api/history/*`** + SQLite / checkpoints, not **`/api/runs`** over `logs/*/0001.json`.

### 7.8 Replay and analytics CLIs

| Legacy | Greenfield |
|--------|------------|
| **`python -m src.eval.replay`** — walks `logs/…/*.json` and **`.ai.json`**, aggregates legality, latency, **token usage per model/profile**, **tool usage** parsed from assistant text | **`src/evaluation/replay.py`** — **LangGraph** replay (`replay_ingress_only`, `replay_with_resume`) for tests; not the same **file-tree analytics** CLI |

### 7.9 Telemetry fields

Legacy traces and **`PersistedAiLog`** carry **planner / combat plan** fields, **validation_error**, per-step **token_usage**, **prompt_profile**, **llm_model_used**, etc. Greenfield **`build_agent_step_event`** (`src/trace_telemetry/schema.py`) records **proposal status**, **emitted_command**, **decision_trace** tail, **failure_streak** — **not** LLM token counts or planner sub-stage metadata on the event.

### 7.10 Operator utilities and ops

- **`archive/legacy_src/src/check_llm.py`** — standalone LLM connectivity check.
- **`prune_old_log_runs`** in legacy **`main.py`** — caps `logs/` directories; greenfield retention is centered on **SQLite / telemetry** (separate policy).
- Legacy **`notify_dashboard`** threads — non-blocking HTTP posts; greenfield uses FastAPI **WebSocket** broadcast from the control API process.

### 7.11 UI delivery

Legacy **embedded HTML** dashboards (`/`, `/ai` in `dashboard.py`). Greenfield **`apps/web`** (React) for monitor / history explorer — different stack, similar operator goals.

---

## 6. Quick reference table

| Concern | Legacy (archive) | Greenfield |
|--------|-------------------|------------|
| Skip LLM when one legal action | Yes (main loop) | No equivalent in mod |
| Auto CONFIRM when only CONFIRM/CANCEL | Yes | No |
| Auto-pick GOLD combat reward | Yes | No |
| `state_id` hash input | Full raw state JSON | Versioned subset (`_FINGERPRINT_KEYS`) |
| `combat_encounter_fingerprint` / `turn_key` | Yes (tracing, prompts) | Not in same form |
| `card_uuid_token` on actions | Yes | Yes (projection) |
| Multi-command decision + queue | `chosen_commands`, `queued_sequence` | Single `emitted_command` |
| Ingress dedupe | Not the same mechanism | Same `state_id` → skip POST |
| Tool use (piles / deck) | Yes (`tool_registry`) | No |
| Combat plan sub-LLM | Optional (`plan_turn`) | No |
| Strategy corpus / rich prompt | Optional | Not in tactical pipeline |
| PLAY `<token>` → canonical PLAY | `resolve_token_play` | Not in `resolve_to_legal_command` |
| Multi-turn LLM history + compaction | `TurnConversation` | Stateless tactical call |
| `poll_instruction` mode + `approved_action` | Yes | Mode stubbed; approval via `/api/agent/resume` |
| File-based `/api/runs` replay | Yes | SQLite / History Explorer |
| Trace: token usage & planner fields | Yes (trace / `.ai.json`) | Partial / different schema |
| Async proposal while game runs | ThreadPoolExecutor | Sync invoke on ingress |

---

## 8. Implementation candidates (from gaps above)

These are **possible** work items if you want closer legacy parity or missing capability; **not** all are desirable for the greenfield architecture.

1. **Tactical correctness**
   - Add **`resolve_token_play`** (or equivalent) to greenfield resolution so models can output **`PLAY <uuid_prefix>`** safely.
   - Reintroduce **main-loop or graph-level short-circuits** (single legal action, CONFIRM/CANCEL-only, combat-reward gold) to cut latency and cost.

2. **LLM depth**
   - Implement a **tool loop** (LangGraph nodes or agent_core) for pile/deck inspection mirroring `tool_registry.py`.
   - Add optional **combat planner** sub-call + encounter-scoped cache (fingerprint keyed), aligned with `13-strategic-planner-collaboration.md` if still a goal.
   - Inject **strategy corpus** or extended prompt sections from `prompt_builder` equivalents.

3. **Multi-command execution**
   - Extend proposal schema and runtime to **`chosen_commands`** + **safe queue** (with strict invalidation on `state_id` / turn change), or document permanent “single command only.”

4. **API / mod wire compatibility**
   - If a single stack must serve both legacy and greenfield clients: align **`poll_instruction`** with real **`agent_mode`** and document **`approved_action`** vs resume flow — or keep greenfield-only contract and document the break explicitly in `README.md`.

5. **Observability and eval**
   - Attach **LLM token usage** and **model id** to trace events or proposal objects when `SLAY_PROPOSER=llm`.
   - Port or replace **legacy `eval.replay` analytics** (metrics over logged runs) using SQLite export or dual readers.

6. **Session memory**
   - Expand greenfield memory beyond **`last_turn`** toward **structured strategy scratchpad** (legacy `strategy_memory`) if long-horizon play quality requires it.

---

*Last updated: 2026-03-25 — extended 2026-03-25 with §§7–8. Aligns with tree under `archive/legacy_src/` and greenfield `src/` as of that date.*
