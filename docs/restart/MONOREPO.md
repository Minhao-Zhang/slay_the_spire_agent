# Monorepo: Python backend + `apps/web` frontend

This repo uses **two toolchains** in one tree:

| Area | Location | Tooling |
| --- | --- | --- |
| Agent runtime, `control_api` | `src/` | **uv** + [`pyproject.toml`](../../pyproject.toml) |
| Operator UI | [`apps/web`](../../apps/web) | **npm** workspaces + Vite + React + TypeScript + Tailwind |

Root [`package.json`](../../package.json) declares `"workspaces": ["apps/*"]`. Install once from the repo root:

```bash
npm install
```

## Local development

1. **Python API** (FastAPI / uvicorn on `http://127.0.0.1:8000`) — run **`run_api.bat`** / **`run_api.sh`** (or `uv run uvicorn src.control_api.app:app --host 127.0.0.1 --port 8000`). Debug routes: `GET /api/debug/snapshot`, `POST /api/debug/ingress`, `WebSocket /ws` (see root [`README.md`](../../README.md)).
2. **Web** — Vite dev server on **port 5173** with **proxy** so the browser uses relative URLs:

   - `GET/POST /api/*` → `http://127.0.0.1:8000`
   - WebSocket `/ws` → `ws://127.0.0.1:8000` (see [`apps/web/vite.config.ts`](../../apps/web/vite.config.ts))

```bash
npm run dev:web
```

Open `http://127.0.0.1:5173`. The UI should call `/api/...` and `new WebSocket` with path `/ws` (same origin as the Vite page).

## Production

- Build the SPA: `npm run build:web` → output in **`apps/web/dist`**.
- Serve **`dist`** from the same ASGI app that exposes `/api` and `/ws` (e.g. `StaticFiles` + SPA fallback so client-side routes work). No CORS needed when UI and API share one origin.

## Policy

- **Do not** import code from `archive/` into `apps/web` or `src/`.
- Contract between UI and API: versioned JSON + stable WS envelope (see [`09-observability-and-debugger-design.md`](09-observability-and-debugger-design.md)).
