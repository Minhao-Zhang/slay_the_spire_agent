"""Persistence and observability settings (Phase 0).

Environment variables (load via python-dotenv from process cwd):

- ``SQL_STATE_MODE``: ``off`` | ``shadow`` | ``primary`` (``primary`` enables SQL-backed ``GET /api/runs`` in the dashboard; agent writes follow the same matrix as ``shadow``).
- ``DATABASE_URL``: Postgres URL when using Postgres (e.g. ``postgresql+psycopg://...``).
- ``SQLITE_PATH``: Path to SQLite file when ``DATABASE_URL`` is unset (default ``data/state.db``).
- ``LANGFUSE_ENABLED``: ``true`` / ``false``.
- ``LANGFUSE_HOST``: API host (e.g. ``https://cloud.langfuse.com``).
- ``LANGFUSE_PUBLIC_KEY``, ``LANGFUSE_SECRET_KEY``: project API keys.
- ``LANGFUSE_SAMPLE_RATE``: float 0.0–1.0 (default 1.0).
- ``LANGFUSE_REDACT_PROMPTS``: ``true`` to hash/truncate prompt text sent to Langfuse.
- ``WRITE_LEGACY_FILE_LOGS``: ``true`` / ``false`` (default ``true``) — gate ``logs/games/`` JSON, sidecars, and ``run_metrics.ndjson`` appends (Phase 0 shadow SQL is independent).
- ``LANGFUSE_FLUSH_INTERVAL_SEC``: seconds between background ``flush()`` calls when ``LANGFUSE_ENABLED`` (default ``25``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class PersistenceSettings:
    sql_state_mode: str  # off | shadow | primary
    database_url: str | None
    sqlite_path: str
    langfuse_enabled: bool
    langfuse_host: str | None
    langfuse_public_key: str | None
    langfuse_secret_key: str | None
    langfuse_sample_rate: float
    langfuse_redact_prompts: bool
    write_legacy_file_logs: bool

    @property
    def sql_shadow_or_primary(self) -> bool:
        return self.sql_state_mode in {"shadow", "primary"}

    def resolved_database_url(self) -> str:
        if self.database_url and self.database_url.strip():
            return self.database_url.strip()
        path = self.sqlite_path.strip() or "data/state.db"
        return f"sqlite:///{path}"


@lru_cache(maxsize=1)
def get_persistence_settings() -> PersistenceSettings:
    load_dotenv()
    mode = (os.getenv("SQL_STATE_MODE", "off") or "off").strip().lower()
    if mode not in {"off", "shadow", "primary"}:
        mode = "off"
    sample_raw = os.getenv("LANGFUSE_SAMPLE_RATE", "1.0") or "1.0"
    try:
        sample = max(0.0, min(1.0, float(sample_raw)))
    except ValueError:
        sample = 1.0
    return PersistenceSettings(
        sql_state_mode=mode,
        database_url=(os.getenv("DATABASE_URL") or "").strip() or None,
        sqlite_path=(os.getenv("SQLITE_PATH", "data/state.db") or "data/state.db").strip(),
        # Design Phase 0: Langfuse on by default; without keys the client stays a no-op.
        langfuse_enabled=(os.getenv("LANGFUSE_ENABLED", "true") or "true").strip().lower() == "true",
        langfuse_host=(os.getenv("LANGFUSE_HOST") or "").strip() or None,
        langfuse_public_key=(os.getenv("LANGFUSE_PUBLIC_KEY") or "").strip() or None,
        langfuse_secret_key=(os.getenv("LANGFUSE_SECRET_KEY") or "").strip() or None,
        langfuse_sample_rate=sample,
        langfuse_redact_prompts=(os.getenv("LANGFUSE_REDACT_PROMPTS", "false") or "false").strip().lower()
        == "true",
        write_legacy_file_logs=(os.getenv("WRITE_LEGACY_FILE_LOGS", "true") or "true").strip().lower()
        == "true",
    )


def reload_persistence_settings() -> PersistenceSettings:
    get_persistence_settings.cache_clear()
    return get_persistence_settings()
