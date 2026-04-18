#!/usr/bin/env python3
"""Backfill historical ``logs/games/<run>`` directories into SQL (Phase 1).

Requires ``SQL_STATE_MODE=shadow`` or ``primary`` and a configured database
(``DATABASE_URL`` or ``SQLITE_PATH``). Uses ``backfill_jobs`` for idempotent resume.

Examples::

    uv run python scripts/backfill_logs.py --logs-root logs/games --dry-run
    uv run python scripts/backfill_logs.py --logs-root logs/games --run my_run_name
    uv run python scripts/backfill_logs.py --logs-root logs/games --all --resume
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.agent.reflection.log_io import iter_frame_json_paths
from src.persistence.backfill_importer import backfill_run_directory
from src.persistence.settings import get_persistence_settings, reload_persistence_settings
from src.persistence.sql_repository import get_sql_repository
from src.persistence.engine import clear_engine_cache


def _discover_run_dirs(logs_root: Path) -> list[Path]:
    if not logs_root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(logs_root.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if iter_frame_json_paths(p):
            out.append(p)
    return out


def _parse_since(s: str) -> dt.datetime:
    raw = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = dt.datetime.strptime(raw, fmt)
            return d.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"invalid --since date: {s!r}")


def main() -> int:
    load_dotenv()
    reload_persistence_settings()

    ap = argparse.ArgumentParser(description="Backfill game log directories into SQL.")
    ap.add_argument("--logs-root", type=Path, required=True, help="Parent of run directories (e.g. logs/games).")
    ap.add_argument("--run", type=str, default="", help="Import a single run directory basename.")
    ap.add_argument("--all", action="store_true", help="Import every child directory that has frame JSON.")
    ap.add_argument("--since", type=_parse_since, default=None, help="UTC date/time; skip dirs older than mtime.")
    ap.add_argument("--dry-run", action="store_true", help="Plan only; no database writes.")
    ap.add_argument("--resume", action="store_true", help="Retry failed jobs (clears partial run + job row).")
    ap.add_argument("--force", action="store_true", help="Re-import even if a prior job succeeded.")
    args = ap.parse_args()

    if not args.run and not args.all:
        print("Specify --run <name> or --all", file=sys.stderr)
        return 2

    settings = get_persistence_settings()
    if not settings.sql_shadow_or_primary:
        print("SQL_STATE_MODE must be shadow or primary for backfill.", file=sys.stderr)
        return 1

    clear_engine_cache()
    reload_persistence_settings()
    repo = get_sql_repository()
    if repo is None:
        print("Could not open SQL repository (check DATABASE_URL / SQLITE_PATH).", file=sys.stderr)
        return 1

    logs_root = args.logs_root.expanduser().resolve()
    dirs = _discover_run_dirs(logs_root)
    if args.run:
        dirs = [logs_root / args.run]
        if not dirs[0].is_dir():
            print(f"Run directory not found: {dirs[0]}", file=sys.stderr)
            return 2

    results: list[dict] = []
    since_ts = args.since.timestamp() if args.since else None
    for d in dirs:
        if since_ts is not None:
            try:
                if d.stat().st_mtime < since_ts:
                    continue
            except OSError:
                continue
        try:
            out = backfill_run_directory(
                repo,
                d,
                dry_run=args.dry_run,
                resume=args.resume,
                force=args.force,
            )
            results.append(out)
            print(json.dumps({"run_dir": d.name, **out}, sort_keys=True))
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"run_dir": d.name, "status": "error", "error": repr(exc)}), file=sys.stderr)
            if not args.dry_run:
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
