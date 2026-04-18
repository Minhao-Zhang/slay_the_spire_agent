"""Phase 0 alignment checks (DESIGN_LOGGING_LANGFUSE_SQL_MIGRATION §5.3, §5.1)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agent.llm_context import LlmCallContext
from src.observability.langfuse_client import langfuse_trace_id_for_decision_id
from src.observability.llm_sql_recording import persist_llm_completion
from src.persistence.engine import clear_engine_cache, get_engine, get_session_factory
from src.persistence.settings import reload_persistence_settings
from src.persistence.sql_repository import SqlRepository

# Subset of DESIGN §5.3 ``stage`` values exercised in Phase 0 code paths (no planner / react_retrieval yet).
PHASE0_LLM_STAGES = frozenset({"decision", "combat_plan", "strategist", "compactor", "reflector"})


@pytest.mark.parametrize("stage", sorted(PHASE0_LLM_STAGES))
def test_phase0_stage_is_design_subset(stage: str) -> None:
    design_stages = frozenset(
        {
            "decision",
            "combat_plan",
            "planner",
            "strategist",
            "react_retrieval",
            "compactor",
            "reflector",
        }
    )
    assert stage in design_stages


def test_reflection_langfuse_trace_is_stable_per_run_name() -> None:
    a = langfuse_trace_id_for_decision_id("reflection:my-run-dir")
    b = langfuse_trace_id_for_decision_id("reflection:my-run-dir")
    assert a == b
    assert len(a) == 32


def test_persist_skips_sql_repository_when_mirror_false(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQL_STATE_MODE", "shadow")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "t.db"))
    clear_engine_cache()
    reload_persistence_settings()

    def boom() -> SqlRepository:
        raise AssertionError("get_sql_repository must not run when mirror_llm_to_sql is False")

    monkeypatch.setattr("src.observability.llm_sql_recording.get_sql_repository", boom)
    lf = MagicMock()
    lf.log_generation.return_value = ("a" * 32, "obs-1")
    monkeypatch.setattr("src.observability.llm_sql_recording.get_langfuse_client", lambda: lf)

    ctx = LlmCallContext(
        run_id=None,
        langfuse_session_id="2026-04-17-12-00-00_IRONCLAD_A0_12345678",
        mirror_llm_to_sql=False,
        langfuse_trace_id=langfuse_trace_id_for_decision_id("reflection:file-run-dir-name"),
        prompt_profile="default",
    )
    persist_llm_completion(
        ctx,
        stage="reflector",
        model="m",
        system_prompt="sys",
        user_blob="user",
        output_text="out",
        usage=None,
        latency_ms=1,
        status="ok",
    )
    lf.log_generation.assert_called_once()
    call_kw = lf.log_generation.call_args.kwargs
    assert call_kw.get("session_id") == "2026-04-17-12-00-00_IRONCLAD_A0_12345678"
    assert call_kw.get("user_id") == "2026-04-17-12-00-00_IRONCLAD_A0_12345678"


def test_persist_writes_sql_when_mirror_true(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQL_STATE_MODE", "shadow")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "t2.db"))
    clear_engine_cache()
    reload_persistence_settings()
    from src.persistence.models import Base

    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    repo = SqlRepository(get_session_factory())
    run_id = "00000000-0000-4000-8000-000000000001"
    repo.create_run(
        {
            "run_id": run_id,
            "run_dir_name": "x",
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
            "langfuse_session_id": "x",
        }
    )

    lf = MagicMock()
    lf.log_generation.return_value = ("c" * 32, "obs-2")
    monkeypatch.setattr("src.observability.llm_sql_recording.get_langfuse_client", lambda: lf)
    monkeypatch.setattr("src.observability.llm_sql_recording.get_sql_repository", lambda: repo)

    ctx = LlmCallContext(
        run_id=run_id,
        langfuse_session_id="x",
        mirror_llm_to_sql=True,
        langfuse_trace_id="d" * 32,
        event_index=0,
        state_id="s",
        client_decision_id="d1",
        prompt_profile="default",
    )
    persist_llm_completion(
        ctx,
        stage="decision",
        model="m",
        system_prompt="sys",
        user_blob="u",
        output_text="o",
        usage=None,
        latency_ms=2,
        status="ok",
    )
    with repo._session() as s:
        from src.persistence.models import LlmCallRow

        n = s.query(LlmCallRow).filter(LlmCallRow.run_id == run_id).count()
    assert n == 1
    lf_kw = lf.log_generation.call_args.kwargs
    assert lf_kw.get("session_id") == "x"
    assert lf_kw.get("user_id") == "x"

    clear_engine_cache()
    reload_persistence_settings()
