# Slay the Spire LLM Bot

LLM-powered assist for Slay the Spire via [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod). The **default Python runtime** is the **legacy agent** in [`src/`](src/) (promoted from [`archive/legacy_src/`](archive/legacy_src/)). The previous **greenfield** rewrite lives under [`archive/greenfield_src/`](archive/greenfield_src/) for reference only.

> [!NOTE]
> Data depends on the [Slay the Spire Reference Spreadsheet](https://docs.google.com/spreadsheets/d/1ZsxNXebbELpcCi8N7FVOTNGdX_K9-BRC_LMgx4TORo4) and CommunicationMod. This project is not affiliated with ForgottenArbiter.

## Repository layout

- **`src/`** — Legacy package: **`python -m src.main`** (game bridge), **`src.ui.dashboard:app`** (FastAPI + Jinja + React compatibility routes).
- **`archive/greenfield_src/`** — Quarantined rewrite (`control_api`, LangGraph, `domain`, …).
- **`archive/legacy_src/`** — Original frozen copy; see [`archive/README.md`](archive/README.md).
- **`apps/web/`** — Vite + React monitor (proxies `/api` and `/ws` to port **8000**).
- **`data/`** — Reference data (spreadsheet extracts, strategy files, etc.).
- **`logs/`** — Run logs and optional local SQLite.

Architecture overview: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Install

Python dependencies are defined in **[`pyproject.toml`](pyproject.toml)** and locked with **`uv.lock`**. Use **`uv sync`** only (no `requirements.txt`).

```bash
uv sync
npm install
```

Optional: copy [`.env.example`](.env.example) to `.env`. Legacy agent config is driven mainly by env vars documented in [`src/agent/config.py`](src/agent/config.py) (e.g. `LLM_API_KEY`, `AGENT_MODE`). `src.main` and the dashboard load `.env` via `python-dotenv` where applicable.

## Run the stack

**Terminal A — dashboard API (port 8000):**

```bash
run_api.bat
```

(or `./run_api.sh`) — `uvicorn src.ui.dashboard:app`

**Terminal B — React monitor (optional):**

```bash
npm run dev:web
```

Open **`http://127.0.0.1:5173/`** for the Vite monitor, or **`http://127.0.0.1:8000/`** for the legacy Jinja UI.

**Terminal C — game bridge:**

```bash
uv run python -m src.main
```

(or `run_agent.bat`). The process prints `ready`, reads JSON lines from stdin, **`POST`s** game state to **`http://localhost:8000/update_state`**, and **`GET`s** **`/poll_instruction`** for manual lines / approved AI commands.

### React monitor API (compatibility layer)

The FastAPI app exposes greenfield-shaped routes for **`apps/web`**: `GET /api/debug/snapshot`, `POST /api/debug/ingress`, `POST /api/debug/manual_command`, `GET /api/debug/poll_instruction`, `POST /api/agent/resume`, `POST /api/agent/retry`, `GET /api/agent/status`, **`WebSocket /ws`** with `{ type: "snapshot", payload }`. **`/api/history/*`** returns empty lists under the legacy backend (History Explorer shows a notice).

### Legacy routes (unchanged)

`POST /update_state`, `GET /poll_instruction`, `POST /api/ai/approve` / `reject`, `GET /api/ai/state`, **`GET /api/runs`**, etc.

## CommunicationMod `command`

Use absolute paths to the repo and `.venv`:

**Windows:**

```properties
command=c:\\PATH\\to\\slay_the_spire_agent\\.venv\\Scripts\\python.exe c:\\PATH\\to\\slay_the_spire_agent\\src\\main.py
```

**macOS / Linux:**

```properties
command=/PATH/TO/slay_the_spire_agent/.venv/bin/python /PATH/TO/slay_the_spire_agent/src/main.py
```

## Scripts

[`scripts/extract_reference_data.py`](scripts/extract_reference_data.py) uses **pandas** / **openpyxl** (still declared in `pyproject.toml`).
