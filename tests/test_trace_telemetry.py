from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.control_api.app import app
from src.trace_telemetry.schema import TRACE_SCHEMA_VERSION, build_agent_step_event
from src.trace_telemetry.store import InMemoryTraceStore

client = TestClient(app)
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_trace_event_schema_version() -> None:
    e = build_agent_step_event(
        thread_id="a",
        step_seq=1,
        step_kind="ingress",
        ts_logical=1.0,
        state_id="sid",
        summary={"proposal": {"status": "idle"}, "decision_trace": [], "failure_streak": 0},
        resume_kind=None,
        idempotency_key=None,
    )
    assert e["schema_version"] == TRACE_SCHEMA_VERSION
    assert e["event_type"] == "agent_step"


def test_idempotent_append_skips_duplicate_key_while_retained() -> None:
    st = InMemoryTraceStore(max_events=100)
    e = {"schema_version": 1, "idempotency_key": "run-1", "x": 1}
    assert st.append(e) is True
    e2 = {"schema_version": 1, "idempotency_key": "run-1", "x": 2}
    assert st.append(e2) is False
    assert len(st.list_events()) == 1
    assert st.list_events()[0]["x"] == 1


def test_store_cap_drops_oldest() -> None:
    st = InMemoryTraceStore(max_events=2)
    st.append({"idempotency_key": "k1", "n": 1})
    st.append({"idempotency_key": "k2", "n": 2})
    st.append({"idempotency_key": "k3", "n": 3})
    ev = st.list_events()
    assert len(ev) == 2
    assert ev[0]["n"] == 2
    assert ev[1]["n"] == 3


def test_idempotency_key_reusable_after_row_evicted() -> None:
    st = InMemoryTraceStore(max_events=1)
    assert st.append({"idempotency_key": "k1", "n": 1}) is True
    assert st.append({"idempotency_key": "k2", "n": 2}) is True
    assert st.list_events()[0]["n"] == 2
    assert st.append({"idempotency_key": "k1", "n": 3}) is True
    assert st.list_events()[0]["n"] == 3


def test_debug_trace_endpoint_after_ingress(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    tr = client.get("/api/debug/trace")
    assert tr.status_code == 200
    body = tr.json()
    assert body["schema_version"] == TRACE_SCHEMA_VERSION
    assert body["count"] >= 1
    assert body["events"][-1]["step_kind"] == "ingress"


def test_trace_disabled_no_append(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_TRACE_ENABLED", "0")
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    tr = client.get("/api/debug/trace")
    assert tr.json()["count"] == 0
