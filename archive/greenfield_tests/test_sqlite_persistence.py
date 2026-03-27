"""Durable SqliteSaver + SqliteTraceStore integration."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.control_api.checkpoint_factory import create_checkpointer
from src.decision_engine.graph import build_agent_graph
from src.trace_telemetry.sqlite_store import SqliteTraceStore


def test_sqlite_trace_store_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    st = SqliteTraceStore(db_path=str(db))
    try:
        assert st.next_step_seq("t1") == 1
        evt = {
            "schema_version": 1,
            "event_type": "agent_step",
            "thread_id": "t1",
            "step_seq": 1,
            "step_kind": "ingress",
            "ts_logical": 1.0,
            "state_id": "s1",
            "idempotency_key": "idem-1",
        }
        assert st.append(evt) is True
        dup = {**evt, "step_seq": 2}
        assert st.append(dup) is False
        evt2 = {**evt, "idempotency_key": "idem-2", "step_seq": 2}
        assert st.append(evt2) is True
        listed = st.list_events(thread_id="t1")
        assert len(listed) == 2
        summaries = st.list_thread_summaries()
        assert len(summaries) == 1
        assert summaries[0]["thread_id"] == "t1"
    finally:
        st.close()


def test_sqlite_checkpointer_survives_new_connection(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "cp.sqlite"
    monkeypatch.setenv("SLAY_CHECKPOINTER", "sqlite")
    monkeypatch.setenv("SLAY_SQLITE_PATH", str(db))

    saver1, conn1 = create_checkpointer()
    assert conn1 is not None
    try:
        g1 = build_agent_graph(checkpointer=saver1)
        cfg: RunnableConfig = {"configurable": {"thread_id": "persist-thread", "agent_mode": "propose"}}
        raw = json.loads(
            (Path(__file__).parent / "fixtures" / "ingress_combat.json").read_text(encoding="utf-8"),
        )
        out = g1.invoke({"ingress_raw": raw}, cfg)
        assert "__interrupt__" in out or out.get("emitted_command")
    finally:
        conn1.close()

    saver2, conn2 = create_checkpointer()
    assert conn2 is not None
    try:
        g2 = build_agent_graph(checkpointer=saver2)
        cfg2: RunnableConfig = {"configurable": {"thread_id": "persist-thread", "agent_mode": "propose"}}
        out2 = g2.invoke(Command(resume="reject"), cfg2)
        assert "proposal" in out2
    finally:
        conn2.close()


def test_history_checkpoints_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_TRACE_BACKEND", "memory")
    from fastapi.testclient import TestClient

    from src.control_api.app import app
    from src.trace_telemetry.runtime import reset_app_trace_store_for_tests

    reset_app_trace_store_for_tests()
    client = TestClient(app)
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "ingress_combat.json").read_text(encoding="utf-8"),
    )
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    h = client.get("/api/history/checkpoints", params={"thread_id": "run-4242424242424242"})
    assert h.status_code == 200
    body = h.json()
    assert "checkpoints" in body
    assert isinstance(body["checkpoints"], list)
    assert len(body["checkpoints"]) >= 1

    cp_id = body["checkpoints"][0].get("checkpoint_id")
    assert cp_id
    det = client.get(
        "/api/history/checkpoint",
        params={"thread_id": "run-4242424242424242", "checkpoint_id": str(cp_id)},
    )
    assert det.status_code == 200
    detail = det.json()
    assert "checkpoint" in detail
    assert "values" in detail["checkpoint"]
    assert "state_id" in detail["checkpoint"]["values"]


def test_history_events_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_TRACE_BACKEND", "memory")
    from fastapi.testclient import TestClient

    from src.control_api.app import app
    from src.trace_telemetry.runtime import reset_app_trace_store_for_tests

    reset_app_trace_store_for_tests()
    client = TestClient(app)
    raw = json.loads(
        (Path(__file__).parent / "fixtures" / "ingress_combat.json").read_text(encoding="utf-8"),
    )
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    h = client.get("/api/history/events")
    assert h.status_code == 200
    body = h.json()
    assert "events" in body
    assert body["count"] >= 1
