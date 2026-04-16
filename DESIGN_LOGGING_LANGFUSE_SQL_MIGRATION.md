# Logging + SQL Migration Design (PM Review Draft)

## 1) Executive Summary

This project migrates run logging from file artifacts (`NNNN.json`, `NNNN.ai.json`, `run_metrics.ndjson`, `run_end_snapshot.json`) to a database-backed model with optional Langfuse correlation.

Decisions locked for this phase:

- Backend supports both `Postgres` and `SQLite` via configuration.
- Frontend changes are intentionally deferred until backend/storage parity is proven.
- Store essential state needed for decision making and replay, not full raw envelopes by default.
- Keep only the final decision record per frame (no intermediate revision history table).
- Keep existing log files during transition; remove later only after parity and rollout validation.
- Langfuse is for observability/debug traces; product-critical analytics and replay must run from SQL.

---

## 2) Scope and Non-Goals

### In scope

- New persistence layer and schema for runs, frames, decisions, and run-end summary.
- Backfill/import from existing logs.
- Validation tooling to compare file-based and DB-based outputs.
- Backend API cutover behind compatibility-preserving response shapes.

### Out of scope (this phase)

- Large frontend refactor.
- Full memory store migration (`data/memory/*.ndjson` remains as-is).
- Perfect byte-for-byte reconstruction of historical JSON files.

---

## 3) Product Contract for This Migration

### Functional reconstruction target

We do **not** require exact byte-equivalent file reconstruction.  
We require **functional reconstruction**:

- enough information to reproduce decision context,
- enough information to preserve replay behavior and metrics,
- enough information for reflection and experiment analysis.

### Storage principle

Persist only fields that materially impact:

- prompt construction,
- legal action validation,
- strategist retrieval context,
- replay and metrics reporting.

---

## 4) Current System Dependencies That Must Be Preserved

- `src/main.py` writes frame logs and sidecars; `write_ai_log` also appends `ai_decision` metrics.
- `src/ui/dashboard.py` replay endpoints currently read `*.ai.json` by frame stem.
- `src/eval/replay.py` and `src/agent/reflection/analyzer.py` currently rely on file artifacts.
- Existing tests assert file-based behaviors and naming contracts.

Migration requirement: APIs and analyzers must continue to produce equivalent outputs from DB.

---

## 5) Architecture Decisions

### 5.1 API boundary

- Browser remains HTTP-only.
- Database access is server-side only (bridge and dashboard backend).
- No service-role credentials in frontend.

### 5.2 Multi-engine DB support

- Single repository interface.
- Runtime config selects `postgres` or `sqlite`.
- SQL dialect differences hidden in repository implementation.

### 5.3 Langfuse role

- Optional but recommended for deep trace observability.
- SQL remains source of truth for product behavior (replay, reflection Tier 1, metrics).
- SQL rows may store `langfuse_trace_id` / generation IDs for correlation links.

---

## 6) Data Model (Logical)

## 6.1 `runs`

Purpose: one row per run.

Required fields:

- `id` (PK)
- `run_dir_name` (legacy compatibility label)
- `seed`
- `character_class`
- `ascension_level`
- `started_at`
- `ended_at`
- `storage_engine` (`postgres` / `sqlite`)
- `status` (`active` / `ended` / `incomplete`)

Optional:

- `source_log_path` (for migration provenance)

## 6.2 `run_frames`

Purpose: decision-relevant frame state by event index.

Key:

- unique `(run_id, event_index)`

Required fields:

- `run_id` (FK)
- `event_index` (int)
- `state_id` (hash id used today)
- `screen_type`
- `floor`
- `act`
- `turn_key`
- `ready_for_command`
- `agent_mode`
- `ai_enabled`
- `command_sent`
- `command_source`
- `action`
- `is_floor_start` (computed)
- `vm_summary_json` (compact summary, equivalent to current `build_vm_summary`)
- `meta_json` (current `meta` compatibility payload)

Decision-context projection (important):

- `state_projection_json` containing only fields used by prompt builder / policy / strategist:
  - `header` (class/floor/act/hp/gold/energy/turn/ascension),
  - `actions` (full normalized legal actions),
  - `combat` (hand, piles, monsters, powers, block, orbs),
  - `inventory` (deck/relics/potions),
  - `screen` content relevant to current screen type,
  - `map` info for path decisions.

Notes:

- We intentionally avoid full raw envelope by default.
- If needed for temporary parity checks, add optional `raw_state_json` behind config.

## 6.3 `agent_decisions`

Purpose: final decision snapshot per frame.

Key:

- unique `(run_id, event_index)` for this phase.

Required fields (sidecar-equivalent):

- `run_id`, `event_index`
- `decision_id`
- `state_id`
- `turn_key`
- `status`
- `approval_status`
- `execution_outcome`
- `final_decision`
- `final_decision_sequence_json`
- `user_message` (or truncated + hash policy if needed)
- `assistant_message` (or truncated + hash policy if needed)
- `validation_error`
- `error`
- `input_tokens`, `output_tokens`, `total_tokens`
- `cached_input_tokens`, `uncached_input_tokens`
- `latency_ms`
- `tool_names_json`
- `planner_summary`
- `combat_plan_generated`
- `combat_plan_text_preview`
- `combat_plan_error`
- `combat_plan_latency_ms`
- `combat_plan_model_used`
- `prompt_profile`
- `llm_model_used`
- `reasoning_effort_used`
- `experiment_tag`, `experiment_id`
- `strategist_ran`
- `lessons_retrieved`
- `retrieved_lesson_ids_json`
- `deck_size`

Optional Langfuse correlation:

- `langfuse_trace_id`
- `langfuse_generation_ids_json`

Design note:

- We store only the final state per frame by decision.
- Intermediate `update_seq` revisions are intentionally not stored in SQL for this phase.

## 6.4 `run_end`

Purpose: one terminal summary row per run.

Key:

- unique `(run_id)`

Required fields:

- `run_id`
- `state_id`
- `victory`
- `score`
- `screen_name`
- `floor`
- `act`
- `gold`
- `current_hp`
- `max_hp`
- `deck_size`
- `relic_count`
- `recorded_at`

## 6.5 Optional `sync_queue` (SQLite durability pattern)

Use only if we need write-behind behavior from SQLite to Postgres.

---

## 7) Decision History Policy

For this phase:

- No intermediate decision revision history table.
- Persist only the final decision snapshot associated with each frame.
- Debug trace depth is delegated to Langfuse and existing runtime logs during transition.

Implication:

- simpler schema and lower storage cost,
- less forensic granularity in SQL alone,
- acceptable per current product direction.

---

## 8) What Counts as "Essential Decision State"

State must include everything used by current decision logic:

- prompt builder inputs (`header`, `inventory`, `combat`, `screen`, `map`, `actions`),
- policy validation against legal actions,
- strategist context tag derivation (class/act/floor/screen/enemies/relics/event/boss),
- replay UI compatibility (`proposal`, `pending_approval`, and metrics summaries).

We should not store unrelated raw ingress fields that do not affect these behaviors.

---

## 9) Repository Interface (Backend)

Suggested operations:

- `create_run(run_identity) -> run_id`
- `insert_frame(run_id, event_index, frame_payload)`
- `upsert_decision_final(run_id, event_index, decision_payload)`
- `upsert_run_end(run_id, run_end_payload)`
- `get_run_metrics(run_id | run_name)`
- `get_frame(run_id, event_index | file_name)`
- `get_frame_decision(run_id, event_index | file_name)`
- `list_runs(filters)`
- `analyze_run_from_db(run_id)`

Requirements:

- idempotent writes for retries,
- deterministic ordering by `event_index`,
- compatibility adapter for legacy API response shapes.

---

## 10) Migration and Rollout Plan

### Phase 0: Foundation

- Create schema and repository for Postgres + SQLite.
- Add config flags to choose engine.

### Phase 1: Backfill from existing logs

- Build importer: `logs/games/*` -> DB tables.
- Support dry-run and per-run import.

### Phase 2: Parity tooling (must pass before cutover)

- Compare file-derived vs DB-derived:
  - frame counts and ordering,
  - decision availability and key fields,
  - run metrics summary,
  - replay proposal payload shape,
  - analyzer/replay aggregate outputs.

### Phase 3: Runtime writes to DB

- Add DB writes in main bridge path for frames, decisions, run-end.
- Keep existing file writes enabled during this phase.

### Phase 4: Backend read cutover

- Update dashboard/replay/metrics endpoints to read DB.
- Preserve existing API JSON contracts so frontend can stay unchanged.

### Phase 5: Frontend follow-up (last)

- Optional cleanup/refactor after backend stability.

### Phase 6: File-write deprecation (future)

- Remove sidecar/NDJSON writes only after sustained parity and operational confidence.

---

## 11) Validation Strategy Using Existing Logs

Use current logs as the regression dataset.

Recommended commands/tools to add:

- backfill tool:
  - `--logs-root`
  - `--run`
  - `--dry-run`
- parity tool:
  - compare analyzer outputs old vs DB,
  - compare metrics summaries old vs DB,
  - compare replay payload equivalents for selected frames.

Acceptance criteria:

- no material drift in run outcome,
- no replay blocking regressions,
- no metrics summary regressions beyond defined tolerance.

---

## 12) Risks and Mitigations

- **Risk:** missing state fields break decision quality.
  - **Mitigation:** explicit essential projection checklist + parity tests.
- **Risk:** SQL behavior diverges between Postgres and SQLite.
  - **Mitigation:** repository-level tests against both engines.
- **Risk:** replay API contract breaks.
  - **Mitigation:** compatibility adapter and snapshot contract tests.
- **Risk:** run archives and zip workflows become inconsistent.
  - **Mitigation:** keep current logs during migration; defer archive redesign.

---

## 13) Open Items (Decision Needed Later)

- Retention policy for full `user_message` / `assistant_message` in SQL.
- Whether optional raw state payload column remains after stabilization.
- If future phases require SQL-stored decision revision history.

---

## 14) One-Line PM Summary

Implement a backend-first, dual-engine (Postgres/SQLite) storage layer that persists essential decision-driving game state and final decisions per frame, proves parity against existing file logs, keeps frontend stable until backend cutover is validated, and uses Langfuse for deep observability rather than core product data dependency.