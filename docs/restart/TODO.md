# Restart implementation checklist

Actionable bootstrap and delivery tasks for the greenfield rewrite. **Detail, verification gates, and scope** for each migration stage are in [`08-migration-plan.md`](08-migration-plan.md).

## Bootstrap (do first)

- [ ] **Step 0 — Archive the current implementation**  
  Move the existing Python tree out of the way so the repo root can host the new layout without losing reference code.  
  - Example: `archive/legacy_src/` or `legacy/src/` containing today’s `src/` contents (e.g. `git mv src archive/legacy_src` on a branch, or copy then remove `src/` if you prefer a clean history).  
  - Update any **local** scripts, IDE configs, or CommunicationMod `command=` paths that still point at `src/main.py`; they should target **`archive/...`** until the new entrypoint exists.  
  - Keep `data/`, `logs/`, `docs/`, etc. at repo root unless you explicitly relocate them.  
  - Commit with a message that records the move so `git log` can find the old paths.

- [ ] **Step 1 — Create the monorepo structure**  
  - Root **`package.json`** with **`workspaces`** (e.g. `"workspaces": ["apps/*"]`) and `private: true`.  
  - Scaffold **`apps/web`** with **Vite + React + TypeScript + Tailwind** (or add a minimal `apps/web/README.md` placeholder until you scaffold).  
  - Decide where the **new** Python package tree will live (e.g. fresh `src/` per [`ARCHITECTURE.md`](ARCHITECTURE.md) suggested layout, or `packages/agent`—document the choice in the root README).  
  - Root **Python** deps: `pyproject.toml` / `uv` / `requirements.txt` aligned with the new tree; `.gitignore` entries for `node_modules/`, `dist/`, build artifacts.  
  - Optional: root `README.md` section describing **two terminals** (`apps/web` dev server + Python API) and env vars.

## Migration stages (from [`08-migration-plan.md`](08-migration-plan.md))

After Steps 0–1, work through these in order; each stage has its own **verification** and **gate** in the migration plan.

- [ ] **Stage 1** — Contracts and serialization spine  
- [ ] **Stage 2** — State projection and legal actions  
- [ ] **Stage 3** — Early debug UI, `control_api`, game ingest (read path; no LangGraph, no LLM)  
- [ ] **Stage 4** — LangGraph shell, checkpointer, `thread_id`  
- [ ] **Stage 5** — Decision engine modes and proposal lifecycle (mocked / no live LLM)  
- [ ] **Stage 6** — HITL interrupts, resume, minimal approval UI  
- [ ] **Stage 7** — LLM gateway and agent core  
- [ ] **Stage 8** — Game adapter write path and full command loop  
- [ ] **Stage 9** — Memory layer  
- [ ] **Stage 10** — Trace telemetry and evaluation  
- [ ] **Stage 11** — Strategic planner (advisory)  
- [ ] **Stage 12** — Full operator UI + streaming  
- [ ] **Stage 13** — SQLite canonical telemetry and history explorer  

## Cutover

- [ ] **Final** — Meet [`08-migration-plan.md`](08-migration-plan.md) **Final cutover criteria**; retire legacy from normal use; update runbooks and root README for the live layout.
