"""Contract-style tests for ``SqlRepository`` (SQLite + optional Postgres)."""

from __future__ import annotations

import os
import uuid

import pytest

from src.persistence.engine import clear_engine_cache, get_engine, get_session_factory
from src.persistence.models import AgentDecisionRow, LlmCallRow, RunEndRow, RunFrameRow, RunRow
from src.persistence.settings import reload_persistence_settings
from src.persistence.sql_repository import SqlRepository


@pytest.fixture
def sqlite_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_STATE_MODE", "shadow")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "state.db"))
    clear_engine_cache()
    reload_persistence_settings()
    from src.persistence.models import Base

    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield SqlRepository(get_session_factory())
    clear_engine_cache()
    reload_persistence_settings()


def _postgres_contract_url() -> str | None:
    u = (os.getenv("PHASE0_CONTRACT_PG_URL") or "").strip()
    return u or None


@pytest.fixture
def pg_repo(monkeypatch):
    url = _postgres_contract_url()
    if not url:
        pytest.skip("PHASE0_CONTRACT_PG_URL not set")
    monkeypatch.setenv("SQL_STATE_MODE", "shadow")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    clear_engine_cache()
    reload_persistence_settings()
    from src.persistence.models import Base

    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield SqlRepository(get_session_factory())
    clear_engine_cache()
    reload_persistence_settings()


def test_create_run_insert_frame_decision_llm(sqlite_repo: SqlRepository) -> None:
    run_id = str(uuid.uuid4())
    sqlite_repo.create_run(
        {
            "run_id": run_id,
            "run_dir_name": "test-run-dir",
            "seed": "1",
            "character_class": "IRONCLAD",
            "ascension_level": 0,
            "storage_engine": "sqlite",
            "system_prompt_hash": "a" * 64,
            "prompt_builder_version": "t",
            "reference_data_hash": None,
            "config_hash": "b" * 64,
            "knowledge_version_id": None,
            "experiment_id": "exp123456789",
            "experiment": {
                "id": "exp123456789",
                "name": "unit",
                "decision_model": "m",
                "reasoning_effort": "low",
                "prompt_profile": "default",
                "config_hash": "b" * 64,
            },
            "source_log_path": "/tmp/x",
            "langfuse_session_id": "test-run-dir",
        }
    )
    fid = str(uuid.uuid4())
    sqlite_repo.insert_frame(
        {
            "frame_id": fid,
            "run_id": run_id,
            "event_index": 0,
            "state_id": "abc123",
            "screen_type": "MAP",
            "floor": 1,
            "act": 1,
            "turn_key": "MAP:1",
            "ready_for_command": True,
            "agent_mode": "propose",
            "ai_enabled": True,
            "command_sent": "state",
            "command_source": "poll",
            "action": None,
            "is_floor_start": False,
            "vm_summary": {"floor": 1},
            "meta": {"event_index": 0},
            "state_projection": {"floor": 1},
        }
    )
    sqlite_repo.record_llm_call(
        {
            "run_id": run_id,
            "frame_id": fid,
            "event_index": 0,
            "state_id": "abc123",
            "client_decision_id": "dec-1",
            "stage": "decision",
            "round_index": 1,
            "model": "gpt-test",
            "reasoning_effort": "low",
            "input_tokens": 10,
            "output_tokens": 2,
            "total_tokens": 12,
            "latency_ms": 50,
            "status": "ok",
            "langfuse_trace_id": "local-" + str(uuid.uuid4()),
            "langfuse_observation_id": "local-" + str(uuid.uuid4()),
            "prompt_profile": "default",
        }
    )
    sqlite_repo.upsert_decision_final(
        {
            "run_id": run_id,
            "event_index": 0,
            "state_id": "abc123",
            "client_decision_id": "dec-1",
            "turn_key": "MAP:1",
            "status": "awaiting_approval",
            "approval_status": "pending",
            "execution_outcome": "",
            "final_decision": "state",
            "final_decision_sequence": ["state"],
            "validation_error": "",
            "error": "",
            "tool_names": [],
            "prompt_profile": "default",
            "experiment_id": "exp123456789",
            "experiment_tag": "",
            "strategist_ran": False,
            "deck_size": 12,
        }
    )
    sqlite_repo.upsert_run_end(
        {
            "run_id": run_id,
            "state_id": "end",
            "victory": True,
            "score": 1234,
            "screen_name": "Victory",
            "floor": 51,
            "act": 3,
            "gold": 99,
            "current_hp": 10,
            "max_hp": 70,
            "deck_size": 20,
            "relic_count": 3,
            "potion_slots": 2,
            "recorded_at": "2026-01-01T00:00:00Z",
        }
    )
    with sqlite_repo._session() as s:
        assert s.get(RunRow, run_id) is not None
        assert s.get(RunFrameRow, fid) is not None
        rows = s.query(LlmCallRow).filter(LlmCallRow.run_id == run_id).all()
        assert len(rows) == 1
        assert rows[0].stage == "decision"
        assert rows[0].reasoning_effort == "low"
        drows = s.query(AgentDecisionRow).filter(AgentDecisionRow.run_id == run_id).all()
        assert len(drows) == 1
        assert drows[0].client_decision_id == "dec-1"
        end = s.get(RunEndRow, run_id)
        assert end is not None
        assert end.victory is True


def test_postgres_contract_matches_sqlite(pg_repo: SqlRepository) -> None:
    """Same flow against Postgres when ``PHASE0_CONTRACT_PG_URL`` is configured."""
    test_create_run_insert_frame_decision_llm(pg_repo)