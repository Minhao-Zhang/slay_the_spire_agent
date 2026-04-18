"""Phase 1: backfill idempotency, RunReport parity, parity CLI, and ``GET /api/runs`` SQL read."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.reflection.analyzer import RunAnalyzer
from src.persistence.backfill_importer import backfill_run_directory
from src.persistence.engine import clear_engine_cache, get_engine, get_session_factory
from src.persistence.backfill_constants import BF_STAGE_FRAMES, BF_STATUS_FAILED
from src.persistence.models import BackfillJobRow, Base, MutationEventRow
from src.persistence.run_report_parity import normalize_run_report_dict
from src.persistence.run_report_view import analyze_run_from_db
from src.persistence.settings import reload_persistence_settings
from src.persistence import sql_repository as sql_repository_mod
from src.persistence.sql_repository import SqlRepository

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "phase1_runs"


@pytest.fixture
def phase1_sqlite_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_STATE_MODE", "shadow")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "phase1.db"))
    clear_engine_cache()
    reload_persistence_settings()
    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield SqlRepository(get_session_factory())
    clear_engine_cache()
    reload_persistence_settings()


def test_backfill_same_fixture_twice_is_idempotent(phase1_sqlite_repo: SqlRepository) -> None:
    d = FIXTURE_ROOT / "phase1_victory"
    r1 = backfill_run_directory(phase1_sqlite_repo, d, dry_run=False, resume=False, force=False)
    assert r1["status"] == "imported"
    rid = r1["run_id"]
    r2 = backfill_run_directory(phase1_sqlite_repo, d, dry_run=False, resume=False, force=False)
    assert r2["status"] == "skipped"
    with phase1_sqlite_repo._session() as s:
        n_jobs = s.query(BackfillJobRow).filter(BackfillJobRow.run_dir == d.name).count()
    assert n_jobs == 1
    row = phase1_sqlite_repo.get_run_row(rid)
    assert row is not None


@pytest.mark.parametrize(
    "run_name",
    ["phase1_victory", "phase1_defeat", "phase1_incomplete"],
)
def test_analyze_run_from_db_matches_file_analyzer(
    phase1_sqlite_repo: SqlRepository,
    run_name: str,
) -> None:
    d = FIXTURE_ROOT / run_name
    out = backfill_run_directory(phase1_sqlite_repo, d, dry_run=False, resume=False, force=True)
    assert out["status"] == "imported"
    file_rep = RunAnalyzer.analyze(d)
    db_rep = analyze_run_from_db(phase1_sqlite_repo, str(out["run_id"]))
    assert normalize_run_report_dict(file_rep.model_dump()) == normalize_run_report_dict(
        db_rep.model_dump()
    )


def test_parity_check_cli_zero_exit(phase1_sqlite_repo: SqlRepository, monkeypatch) -> None:
    """Subprocess uses its own env: point at the same SQLite file as the populated repo."""
    with phase1_sqlite_repo._session() as s:
        db_path = s.get_bind().url.database  # type: ignore[union-attr]
    assert isinstance(db_path, str) and db_path
    for name in ("phase1_victory", "phase1_defeat", "phase1_incomplete"):
        backfill_run_directory(phase1_sqlite_repo, FIXTURE_ROOT / name, dry_run=False, force=True)

    repo_root = Path(__file__).resolve().parents[1]
    env = {**__import__("os").environ, "SQL_STATE_MODE": "shadow", "DATABASE_URL": "", "SQLITE_PATH": str(db_path)}
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "parity_check.py"),
        "--logs-root",
        str(FIXTURE_ROOT),
        "--all",
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_get_api_runs_primary_matches_file_list(monkeypatch, tmp_path, phase1_sqlite_repo: SqlRepository) -> None:
    from src.ui import dashboard

    log_games = tmp_path / "logs" / "games"
    log_games.mkdir(parents=True)
    for name in ("phase1_victory", "phase1_defeat"):
        (log_games / name).mkdir()
    monkeypatch.setattr(dashboard, "LOG_GAMES_DIR", str(log_games))
    monkeypatch.setattr(dashboard, "LOGS_DIR", str(tmp_path / "logs"))

    for name in ("phase1_victory", "phase1_defeat"):
        backfill_run_directory(phase1_sqlite_repo, FIXTURE_ROOT / name, dry_run=False, force=True)

    monkeypatch.setenv("SQL_STATE_MODE", "shadow")
    clear_engine_cache()
    reload_persistence_settings()

    file_payload = asyncio.run(dashboard.get_runs())
    assert file_payload == {"runs": ["phase1_victory", "phase1_defeat"], "archived": {}}

    monkeypatch.setenv("SQL_STATE_MODE", "primary")
    clear_engine_cache()
    reload_persistence_settings()

    monkeypatch.setattr(sql_repository_mod, "get_sql_repository", lambda: phase1_sqlite_repo)
    sql_payload = asyncio.run(dashboard.get_runs())
    assert sql_payload == file_payload


def test_backfill_rolls_back_data_on_mid_import_failure(
    phase1_sqlite_repo: SqlRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inject failure during frame import; run row must not exist and job must be failed."""
    d = FIXTURE_ROOT / "phase1_victory"
    calls = {"n": 0}
    orig = SqlRepository.insert_frame_in_session

    def flaky_insert(self, session, payload):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("injected_frame_failure")
        return orig(self, session, payload)

    monkeypatch.setattr(SqlRepository, "insert_frame_in_session", flaky_insert)
    with pytest.raises(RuntimeError, match="injected_frame_failure"):
        backfill_run_directory(phase1_sqlite_repo, d, dry_run=False, force=True)
    assert phase1_sqlite_repo.get_run_row_by_dir_name(d.name) is None
    job = phase1_sqlite_repo.get_backfill_job_by_run_dir(d.name)
    assert job is not None
    assert job.status == BF_STATUS_FAILED
    assert job.stage == BF_STAGE_FRAMES


def test_backfill_mutation_events_use_migration_actor(phase1_sqlite_repo: SqlRepository) -> None:
    d = FIXTURE_ROOT / "phase1_defeat"
    out = backfill_run_directory(phase1_sqlite_repo, d, dry_run=False, force=True)
    assert out["status"] == "imported"
    rid = str(out["run_id"])
    with phase1_sqlite_repo._session() as s:
        rows = (
            s.query(MutationEventRow)
            .filter(MutationEventRow.after_json.isnot(None))
            .all()
        )
    matched = [
        m
        for m in rows
        if isinstance(m.after_json, dict) and m.after_json.get("run_id") == rid
    ]
    assert matched, "expected mutation_events referencing imported run_id"
    assert all(m.actor == "migration" for m in matched)
    assert any(m.action == "insert_frame" for m in matched)
