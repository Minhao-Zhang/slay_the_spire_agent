#!/usr/bin/env python3
"""Compare :class:`RunReport` from disk vs SQL-backed assembly (Phase 1).

Requires the run to exist in SQL (typically after ``scripts/backfill_logs.py``).

Examples::

    uv run python scripts/parity_check.py --logs-root tests/fixtures/phase1_runs --all
    uv run python scripts/parity_check.py --logs-root tests/fixtures/phase1_runs --run phase1_victory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.agent.reflection.analyzer import RunAnalyzer
from src.agent.reflection.log_io import iter_frame_json_paths
from src.persistence.run_report_parity import normalize_run_report_dict
from src.persistence.run_report_view import analyze_run_from_db
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


def _diff_summary(a: dict, b: dict) -> str:
    keys = sorted(set(a.keys()) | set(b.keys()))
    lines: list[str] = []
    for k in keys:
        if a.get(k) != b.get(k):
            lines.append(f"  {k!r}: file={a.get(k)!r} ... db={b.get(k)!r}")
    return "\n".join(lines[:40]) + ("\n  ..." if len(lines) > 40 else "")


def main() -> int:
    load_dotenv()
    reload_persistence_settings()

    ap = argparse.ArgumentParser(description="Run RunReport parity: file analyzer vs analyze_run_from_db.")
    ap.add_argument("--logs-root", type=Path, required=True)
    ap.add_argument("--run", type=str, default="")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if not args.run and not args.all:
        print("Specify --run <name> or --all", file=sys.stderr)
        return 2

    settings = get_persistence_settings()
    if not settings.sql_shadow_or_primary:
        print("SQL_STATE_MODE must be shadow or primary.", file=sys.stderr)
        return 1

    clear_engine_cache()
    reload_persistence_settings()
    repo = get_sql_repository()
    if repo is None:
        print("Could not open SQL repository.", file=sys.stderr)
        return 1

    logs_root = args.logs_root.expanduser().resolve()
    dirs = _discover_run_dirs(logs_root)
    if args.run:
        dirs = [logs_root / args.run]
        if not dirs[0].is_dir():
            print(f"Run directory not found: {dirs[0]}", file=sys.stderr)
            return 2

    failed = False
    for d in dirs:
        row = repo.get_run_row_by_dir_name(d.name)
        if not row:
            print(f"[{d.name}] SKIP: no SQL run for run_dir_name (run backfill first)", file=sys.stderr)
            failed = True
            continue
        file_rep = RunAnalyzer.analyze(d)
        db_rep = analyze_run_from_db(repo, row.id)
        fa = normalize_run_report_dict(file_rep.model_dump())
        fb = normalize_run_report_dict(db_rep.model_dump())
        if fa != fb:
            print(f"[{d.name}] MISMATCH\n{_diff_summary(fa, fb)}", file=sys.stderr)
            failed = True
        else:
            print(json.dumps({"run": d.name, "ok": True}))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
