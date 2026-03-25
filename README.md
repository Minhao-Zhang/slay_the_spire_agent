# Slay the Spire LLM Bot

This project aims to create an LLM-powered bot capable of playing Slay the Spire.

> [!NOTE]
> This project depends on data from the [Slay the Spire Reference Spreadsheet](https://docs.google.com/spreadsheets/d/1ZsxNXebbELpcCi8N7FVOTNGdX_K9-BRC_LMgx4TORo4) and the [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) mod. Both of these resources were created by [ForgottenArbiter](https://github.com/ForgottenArbiter). This project is not affiliated with ForgottenArbiter. However, I would like to thank him for his hard work and dedication to the Slay the Spire community.

## Repository layout

- **`src/`** — **Greenfield** Python package (the only code `uv` installs). Entrypoint: `python -m src.main`. **`src/game_adapter/`**, **`src/domain/`**, **`src/decision_engine/`**, **`src/control_api/`**, **`src/llm_gateway/`**, **`src/agent_core/`**, **`src/memory/`** (bounded episodic log + namespaced store). Do **not** import from `archive/`.
- **`archive/legacy_src/`** — Historical snapshot for **reference only** (read [`archive/README.md`](archive/README.md)).
- **`apps/web/`** — Vite + React + TypeScript + Tailwind operator UI (workspace **`@slay/web`**). Dev server proxies `/api` and `/ws` to `127.0.0.1:8000`. See [`docs/restart/MONOREPO.md`](docs/restart/MONOREPO.md) and [`apps/web/README.md`](apps/web/README.md).
- **`data/`**, **`logs/`**, **`docs/`** — Game data, runtime logs, and documentation.

Greenfield plans and staged migration: [`docs/restart/README.md`](docs/restart/README.md).

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

Open `http://127.0.0.1:5173`, click **Load sample state**, or paste a CommunicationMod-style JSON object and **Apply projection**. The UI reflects `project_state` output (actions, hand, monsters, etc.).

- `GET /api/debug/snapshot` — latest snapshot  
- `GET /api/debug/trace` — schema-versioned agent-step trace events (`limit`, optional `thread_id`)  
- `POST /api/debug/ingress` — body = raw ingress JSON → projection + broadcast  
- `POST /api/debug/manual_command` — `{ "command": "..." }` must match the **current** legal action list (load ingress first); canonical string is queued for `main.py`  
- `GET /api/debug/poll_instruction` — pop one queued manual command (`manual_action`) for `python -m src.main`  
- `GET /api/agent/status` — LangGraph agent + pending approval (HITL)  
- `POST /api/agent/resume` — body `kind`: `approve`, `reject`, or `edit` (optional `command` for edit); continues after interrupt; `approve` queues the proposed command  
- `WebSocket /ws` — `{ type: "snapshot", payload: {...} }`; `payload.agent` has pending approval and env-derived mode/thread.

**Agent mode (API process env):** `SLAY_AGENT_MODE` = `propose` (default, interrupt in UI), `auto`, or `manual`. `SLAY_AGENT_THREAD_ID` defaults to `default`. **Stage 7:** `SLAY_PROPOSER` = `mock` (default, first legal action) or `llm` (JSON proposal via `agent_core`); `SLAY_LLM_BACKEND` = `stub` (default, offline) or `openai` (needs `OPENAI_API_KEY`; `SLAY_OPENAI_MODEL` defaults to `gpt-5.4`). **Stage 9:** `SLAY_MEMORY_MAX_TURNS` (default `32`, cap `10000`) bounds episodic `memory_log` in the LangGraph state; long-term dev store is in-process (`src/memory/`). **Stage 10:** `SLAY_TRACE_ENABLED` (default on; set `0`/`false`/`off` to stop appending to the in-memory trace ring); `SLAY_TRACE_MAX_EVENTS` caps retained rows. CI replay: `src/evaluation/replay.py` (`replay_ingress_only`, `replay_with_resume`) with fixed `configurable.now` and an `InMemoryTraceStore` passed as `trace_store` (or rely on the default app store when recording is enabled).

**Live game (CommunicationMod):** start `run_api.bat` / `run_api.sh`, then point the mod at `python -m src.main` (or `run_agent.bat`). Each stdin JSON line is posted to the control API (set `SLAY_CONTROL_API_URL` if the API is not on `http://127.0.0.1:8000`). When `ready_for_command` is true, the runner prints a **Valid Actions** click, an **agent-approved** command from the monitor, else `wait 10` / `state`, else `state`. Run the web monitor for manual actions and (in `propose` mode) approvals.

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

## Running the agent (stub)

The CommunicationMod entrypoint is wired to the **new** package:

```bash
uv run python -m src.main
```

Or: `run_agent.bat` (Windows) / `run_agent.sh` (Unix).

**Current behavior:** a bootstrap stub (see [`src/main.py`](src/main.py)) until the rewrite implements the `game_adapter` loop per [`docs/restart/08-migration-plan.md`](docs/restart/08-migration-plan.md).

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

## Replay evaluation (planned)

The **debug monitor** (`control_api` + `apps/web`) is available (see above). **Replay** metrics / CLI against recorded logs are still to be reimplemented in the greenfield tree per the migration plan—not by reusing archived modules.
