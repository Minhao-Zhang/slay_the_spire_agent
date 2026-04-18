#!/usr/bin/env python3
"""Check persistence / database configuration: URL, engine, optional shadow write.

Run from repo root (loads ``.env`` via the same settings as the bridge):

    uv run python scripts/check_database_config.py

Or:

    python scripts/check_database_config.py
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from src.persistence.engine import clear_engine_cache, get_engine
from src.persistence.settings import get_persistence_settings, reload_persistence_settings
from src.persistence.sql_repository import get_sql_repository


def _mask_url(url: str) -> str:
    """Hide password in ``postgresql://user:pass@host/...`` style URLs."""
    return re.sub(r"(//[^/:]+:)([^@]+)(@)", r"\1****\3", url, count=1)


def main() -> int:
    clear_engine_cache()
    reload_persistence_settings()
    s = get_persistence_settings()
    url = s.resolved_database_url()

    print("--- Persistence settings (from .env / environment) ---")
    print(f"  SQL_STATE_MODE:        {s.sql_state_mode!r}")
    print(f"  sql_shadow_or_primary: {s.sql_shadow_or_primary}")
    print(f"  DATABASE_URL set:      {bool(s.database_url)}")
    print(f"  SQLITE_PATH:           {s.sqlite_path!r}")
    print(f"  WRITE_LEGACY_FILE_LOGS: {s.write_legacy_file_logs}")
    print(f"  Resolved DB URL:       {_mask_url(url)}")
    print()

    if not s.sql_shadow_or_primary:
        print(
            "NOTE: SQL_STATE_MODE is not 'shadow' or 'primary'.\n"
            "      The bridge will not set sql_run_id or write frames/decisions to SQL.\n"
            "      Set SQL_STATE_MODE=shadow in .env and restart the bridge.\n"
        )

    print("--- Engine connectivity ---")
    try:
        eng = get_engine()
        with eng.connect() as conn:
            one = conn.execute(text("SELECT 1")).scalar_one()
        print(f"  OK: SELECT 1 -> {one!r} (dialect={eng.dialect.name})")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: could not connect or query: {exc!r}")
        return 1

    print()
    print("--- Shadow repository (only when SQL_STATE_MODE is shadow|primary) ---")
    try:
        repo = get_sql_repository()
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: get_sql_repository() raised: {exc!r}")
        return 1

    if repo is None:
        print("  (skipped — get_sql_repository() returned None; shadow/primary off or engine unavailable)")
        print()
        print("check_database_config: OK (connectivity only)")
        return 0

    run_id = str(uuid.uuid4())
    exp_id = "check-database-config-exp"
    try:
        repo.create_run(
            {
                "run_id": run_id,
                "run_dir_name": f"__db_check__/{run_id[:8]}",
                "seed": "0",
                "character_class": "IRONCLAD",
                "ascension_level": 0,
                "storage_engine": "postgres" if eng.dialect.name == "postgresql" else "sqlite",
                "system_prompt_hash": "0" * 64,
                "prompt_builder_version": "check_database_config",
                "reference_data_hash": None,
                "config_hash": "1" * 64,
                "knowledge_version_id": None,
                "experiment_id": exp_id,
                "experiment": {
                    "id": exp_id,
                    "name": "database-config-check",
                    "decision_model": "n/a",
                    "reasoning_effort": "low",
                    "prompt_profile": "default",
                    "config_hash": "1" * 64,
                },
                "source_log_path": str(ROOT / "scripts" / "check_database_config.py"),
                "langfuse_session_id": f"__db_check__/{run_id[:8]}",
            }
        )
        from src.persistence.models import RunRow

        with repo._session() as session:
            row = session.get(RunRow, run_id)
        if row is None:
            print("  FAIL: create_run succeeded but row not found on read-back")
            return 1
        print(f"  OK: wrote and read back runs.id = {run_id[:8]}…")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL: create_run / read-back: {exc!r}")
        return 1

    print()
    print("check_database_config: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
