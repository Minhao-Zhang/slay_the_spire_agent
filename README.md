# Slay the Spire LLM Bot

This project aims to create an LLM-powered bot capable of playing Slay the Spire.

> [!NOTE]
> This project depends on data from the [Slay the Spire Reference Spreadsheet](https://docs.google.com/spreadsheets/d/1ZsxNXebbELpcCi8N7FVOTNGdX_K9-BRC_LMgx4TORo4) and the [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) mod. Both of these resources were created by [ForgottenArbiter](https://github.com/ForgottenArbiter). This project is not affiliated with ForgottenArbiter. However, I would like to thank him for his hard work and dedication to the Slay the Spire community.

## Repository layout

- **`src/`** — **Greenfield** Python package (the only code `uv` installs). Entrypoint: `python -m src.main`. Major areas: **`src/game_adapter/`**, **`src/domain/`**, **`src/decision_engine/`**, **`src/control_api/`**, **`src/llm_gateway/`**, **`src/agent_core/`**, **`src/memory/`**, **`src/trace_telemetry/`**, **`src/evaluation/`** (test replay helpers). Do **not** import from `archive/`.
- **`archive/legacy_src/`** — Historical snapshot for **reference only** (read [`archive/README.md`](archive/README.md)).
- **`apps/web/`** — Vite + React + TypeScript + Tailwind operator UI (workspace **`@slay/web`**). Dev server proxies `/api` and `/ws` to `127.0.0.1:8000`. See [`docs/restart/MONOREPO.md`](docs/restart/MONOREPO.md) and [`apps/web/README.md`](apps/web/README.md).
- **`data/`**, **`logs/`**, **`docs/`** — Game data, runtime logs, and documentation.

**As-built architecture (data flow, endpoints, gaps):** [`ARCHITECTURE.md`](ARCHITECTURE.md). Target design and migration specs: [`docs/restart/README.md`](docs/restart/README.md).

### Monorepo: install both toolchains

```bash
uv sync          # Python (.venv)
npm install      # Node (workspaces; installs apps/web)
```

Optional: copy [`.env.example`](.env.example) to `.env` and set variables (e.g. `OPENAI_API_KEY` when using `SLAY_LLM_BACKEND=openai`). `src.main` and `src.control_api.app` call `load_dotenv()` so the file is picked up on startup.

Run the web app (**control API** must be on port **8000** — use `run_api.bat` / `run_api.sh`):

```bash
npm run dev:web
```

### Debug monitor (state projection UI)

Two terminals:

```bash
run_api.bat
```

(or `./run_api.sh` on Unix) — FastAPI **control API** on `http://127.0.0.1:8000`

```bash
npm run dev:web
```

— Vite on port **5173**; it **proxies** `/api` and `/ws` to port 8000.

Open **`http://127.0.0.1:5173/`** for the **monitor** (command center): click **Load sample state**, or paste CommunicationMod-style JSON and **Apply projection**. The UI reflects `project_state` output (actions, hand, monsters, etc.).

Open **`http://127.0.0.1:5173/explorer`** for the **History Explorer** (thread picker, trace + checkpoint timeline, checkpoint JSON). Optional query: **`?thread_id=run-…`** to pre-select a run; the monitor’s **History** link passes the current agent `thread_id`.

- `GET /api/debug/snapshot` — latest snapshot  
- `GET /api/debug/trace` — schema-versioned agent-step trace events (`limit`, optional `thread_id`)  
- `POST /api/debug/ingress` — body = raw ingress JSON → projection + broadcast  
- `POST /api/debug/manual_command` — `{ "command": "..." }` must match the **current** legal action list (load ingress first); canonical string is queued for `main.py`  
- `GET /api/debug/poll_instruction` — pop one queued manual command (`manual_action`) for `python -m src.main`  
- `GET /api/agent/status` — LangGraph agent + pending approval (HITL)  
- `POST /api/agent/resume` — body `kind`: `approve`, `reject`, or `edit` (optional `command` for edit); continues after interrupt; `approve` queues the proposed command  
- `POST /api/agent/retry` — re-run the graph on the snapshot’s current ingress (skips unchanged-state short-circuit; clears pending interrupt via reject when needed)  
- `GET /api/history/threads` — distinct `thread_id` summaries from stored agent-step events (optional query `merge_checkpoint_threads=true` when using SQLite checkpoints to include threads that only exist in the checkpoint DB)  
- `GET /api/history/events` — paginated trace events (`thread_id`, `limit`, `offset`)  
- `GET /api/history/checkpoints` — LangGraph checkpoint timeline for a `thread_id`  
- `GET /api/history/checkpoint` — one checkpoint’s state (`thread_id`, optional `checkpoint_id`, `checkpoint_ns`); serialized `values` use an allowlist; set `SLAY_DEBUG_HISTORY_STATE=1` to include raw `ingress_raw` in that payload  
- `WebSocket /ws` — `{ type: "snapshot", payload: {...} }`; `payload.agent` has pending approval and env-derived mode/thread.

**Agent mode (API process env):** `SLAY_AGENT_MODE` = `propose` (default, interrupt in UI), `auto`, or `manual`. LangGraph `thread_id` comes from CommunicationMod `game_state.seed` (`run-{seed}`) or `run-menu` when not in-game / seed missing. **Stage 7:** `SLAY_PROPOSER` = `mock` (default, first legal action) or `llm` (JSON proposal via `agent_core`); `SLAY_LLM_BACKEND` = `stub` (default, offline) or `openai` (needs `OPENAI_API_KEY`; `SLAY_OPENAI_MODEL` defaults to `gpt-5.4`). **Stage 9:** `SLAY_MEMORY_MAX_TURNS` (default `32`, cap `10000`) bounds episodic `memory_log` in the LangGraph state; long-term dev store is in-process (`src/memory/`). **Persistence:** `SLAY_CHECKPOINTER` = `memory` (default) or `sqlite` (durable LangGraph checkpoints in `SLAY_SQLITE_PATH`, default `logs/slay_agent.sqlite`). **Trace:** `SLAY_TRACE_ENABLED` (default on); `SLAY_TRACE_BACKEND` = `memory` or `sqlite` (same DB file when sqlite); `SLAY_TRACE_MAX_EVENTS` caps **memory** backend only. CI replay: `src/evaluation/replay.py` with `InMemoryTraceStore` or injected `trace_store`.

**Live game (CommunicationMod):** start `run_api.bat` / `run_api.sh`, then point the mod at `python -m src.main` (or `run_agent.bat`). Each stdin JSON line is posted to the control API when the payload’s `state_id` changes (set `SLAY_CONTROL_API_URL` if the API is not on `http://127.0.0.1:8000`). When `ready_for_command` is true, the runner prints the next **queued** command from the monitor (manual submit or agent `auto` / approved `propose`), if legal; otherwise it prints `wait 10` or `state` when those appear in `available_commands`, else `state`. Use the web monitor for manual actions and (in `propose` mode) approvals.

## Setup (uv)

Python dependencies are declared in [`pyproject.toml`](pyproject.toml). Use **[uv](https://docs.astral.sh/uv/)**:

```bash
uv sync
```

This creates `.venv` and installs the project in editable mode so `import src` works.

The file [`requirements.txt`](requirements.txt) is deprecated; prefer `uv sync`.

Install dev tools (e.g. pytest) and run tests:

```bash
uv sync --group dev
uv run pytest
```

## Running the agent (CommunicationMod)

The CommunicationMod subprocess entrypoint is [`src/main.py`](src/main.py):

```bash
uv run python -m src.main
```

Or: `run_agent.bat` (Windows) / `run_agent.sh` (Unix).

**Current behavior:** prints `ready`, reads JSON lines from stdin, and when the control API is reachable:

- **Ingress sync:** POSTs each distinct game payload to `POST /api/debug/ingress` (skips duplicates using the same `state_id` as the API).
- **Commands:** when `ready_for_command` is true, polls `GET /api/debug/poll_instruction` for a queued operator/agent command; if present, validates it against the **current** projected legal actions, then prints it; otherwise prefers `wait 10` or `state` from `available_commands`, else `state`.

Without the API, ingress sync and queued commands are skipped; idle/`state` fallback still runs. Further migration items (e.g. richer game-loop policy, full spec-16 telemetry tables) are tracked in [`docs/restart/08-migration-plan.md`](docs/restart/08-migration-plan.md).

## Communication Mod configuration

Point Communication Mod at your uv-managed Python and this repo’s **`src/main.py`** (absolute paths), for example:

**Windows (`config.properties`):**

```properties
command=c:\\ABSOLUTE\\PATH\\to\\slay_the_spire_agent\\.venv\\Scripts\\python.exe c:\\ABSOLUTE\\PATH\\to\\slay_the_spire_agent\\src\\main.py
```

**macOS / Linux:**

```properties
command=/ABSOLUTE/PATH/TO/slay_the_spire_agent/.venv/bin/python /ABSOLUTE/PATH/TO/slay_the_spire_agent/src/main.py
```

## Replay evaluation

**In place today:** [`src/evaluation/replay.py`](src/evaluation/replay.py) runs the compiled LangGraph deterministically for tests—`replay_ingress_only`, `replay_with_resume`, optional `InMemoryTraceStore`, and fixed `configurable.now` (see [`src/decision_engine/proposal_logic.py`](src/decision_engine/proposal_logic.py) `graph_now`). Used from pytest (`tests/test_evaluation_replay.py`), not as a standalone operator CLI.

**Not in greenfield yet:** a **user-facing** replay tool over on-disk CommunicationMod / run logs (like the archived `python -m …eval.replay` flow) and a run browser (**`GET /api/runs`**). **Minimal** SQLite checkpoints + `trace_events` + `/api/history/*` + web **History** rail on the monitor and a dedicated **`/explorer`** History Explorer page are implemented; the full multi-table schema in [`docs/restart/16-sqlite-telemetry-and-history-explorer-spec.md`](docs/restart/16-sqlite-telemetry-and-history-explorer-spec.md) is still future work.
