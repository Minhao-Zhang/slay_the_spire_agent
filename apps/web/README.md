# Operator UI (`@slay/web`)

Vite + React + TypeScript + Tailwind. In development, **`/api`** and **`/ws`** are proxied to the **legacy** Python dashboard at **`127.0.0.1:8000`** (`uvicorn src.ui.dashboard:app`; see `vite.config.ts`).

**Routes:** **`/`** — monitor (projection + HITL). **`/explorer`** — History Explorer (history APIs are stubs on legacy; page shows a note). Start the dashboard on port 8000 before `npm run dev:web`.

From the **repository root**:

```bash
npm install
npm run dev:web
```

Build:

```bash
npm run build:web
```

Output: `apps/web/dist/` (mount from FastAPI in production).

Layout: Python dashboard and game bridge live at the repo root; this package is the Vite operator UI only (`/` and `/explorer`).
