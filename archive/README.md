# Archived reference

- **`legacy_src/`** — Original frozen copy of the **pre–greenfield** Python tree (still useful for diffs). The **authoritative runnable code** now lives in the repo root **`src/`**, promoted from this snapshot.

- **`greenfield_src/`** — The **prior rewrite** (LangGraph `control_api`, `domain`, `agent_core`, etc.), quarantined when switching the default runtime back to the legacy agent loop.

- **`greenfield_tests/`** — Pytest suite for the greenfield package; not run against the current `src/` layout without changes.

Use [`uv`](https://docs.astral.sh/uv/) and [`pyproject.toml`](../pyproject.toml) at the repo root; **`python -m src.main`** + **`src.ui.dashboard:app`** are the live entrypoints.
