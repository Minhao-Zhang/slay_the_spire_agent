# Operator UI (`@slay/web`)

Vite + React + TypeScript + Tailwind. In development, **`/api`** and **`/ws`** are proxied to the Python control API at **`127.0.0.1:8000`** (see `vite.config.ts`).

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

See [`docs/restart/MONOREPO.md`](../docs/restart/MONOREPO.md) for the full front/back layout.
