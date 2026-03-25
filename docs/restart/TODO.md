# Restart implementation checklist

Actionable bootstrap and delivery tasks for the greenfield rewrite. **Detail, verification gates, and scope** for each migration stage are in [`08-migration-plan.md`](08-migration-plan.md).

## Bootstrap (do first)

- [x] **Step 0 — Archive the current implementation**  
  Legacy code lives under `archive/legacy_src/` for **reference only** — do not import or reuse it in the new `src/` package (see [`archive/README.md`](../../archive/README.md)).

- [x] **Step 1 — Create the monorepo structure**  
  - Root **`pyproject.toml`** + **`uv sync`** for the Python package (editable `src/`).  
  - Root **`package.json`** workspaces + **`apps/web`** (Vite + React + TS + Tailwind; proxy `/api` + `/ws` → port 8000). See [`MONOREPO.md`](MONOREPO.md).  
  - `.gitignore` includes `node_modules/`; `dist/` is ignored.

## Migration stages (from [`08-migration-plan.md`](08-migration-plan.md))

After Steps 0–1, work through these in order; each stage has its own **verification** and **gate** in the migration plan.

- [x] **Stage 1** — Contracts and serialization spine (`src/domain/contracts/`, `state_id`, pytest)  
- [x] **Stage 2** — State projection and legal actions (`src/domain/state_projection/`, fixtures under `tests/fixtures/`)  
- [x] **Stage 3** — Early debug UI, `control_api`, game ingest (read path; no LangGraph, no LLM)  
  - Optional later: richer parity with legacy modes (queued sequences).  
- [x] **Stage 4** — LangGraph shell, checkpointer, `thread_id` (`src/decision_engine/graph.py`, pytest)  
- [x] **Stage 5** — Decision engine modes and proposal lifecycle (mocked / no live LLM; `decision_engine/graph.py`, `proposal_logic.py`, pytest)  
- [x] **Stage 6** — HITL via `control_api`: agent graph on ingress, `GET /api/agent/status`, `POST /api/agent/resume`; snapshot + WS include `agent`; debug UI approval panel; `SLAY_AGENT_MODE` / `SLAY_AGENT_THREAD_ID`  
- [x] **Stage 7** — LLM gateway (`src/llm_gateway/`) + agent core (`src/agent_core/`); `SLAY_PROPOSER=mock|llm`, `SLAY_LLM_BACKEND=stub|openai`; graph uses `propose_for_view_model`  
- [x] **Stage 8** — Game adapter (`src/game_adapter/`) + `domain.legal_command`; validated enqueue in `control_api`; `main.py` validates poll + idle before emit  
- [x] **Stage 9** — Memory layer (`src/memory/`: bounded `memory_log` in graph, `InMemoryMemoryStore` namespaces; `SLAY_MEMORY_MAX_TURNS`)  
- [x] **Stage 10** — Trace telemetry and evaluation (`src/trace_telemetry/`, `src/evaluation/replay.py`; `GET /api/debug/trace`; `SLAY_TRACE_ENABLED`, `SLAY_TRACE_MAX_EVENTS`; optional `trace_idempotency_key` / `trace_store` in LangGraph `configurable`)  
- [ ] **Stage 11** — Strategic planner (advisory)  
- [ ] **Stage 12** — Full operator UI + streaming  
- [ ] **Stage 13** — SQLite canonical telemetry and history explorer  

## Cutover

- [ ] **Final** — Meet [`08-migration-plan.md`](08-migration-plan.md) **Final cutover criteria**; retire legacy from normal use; update runbooks and root README for the live layout.
