from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.control_api.app as control_app
import src.control_api.agent_runtime as agent_runtime
from src.control_api.app import app

client = TestClient(app)
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_manual_command_queue() -> None:
    with control_app._instruction_lock:
        control_app._manual_command_queue.clear()


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_debug_ingress_round_trip() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    data = r.json()
    assert data["state_id"] is not None
    assert data["view_model"] is not None
    assert data["view_model"]["in_game"] is True
    assert len(data["view_model"]["actions"]) >= 1


def test_debug_ingress_skips_reprojection_when_state_id_unchanged(monkeypatch) -> None:
    """Game / CommMod often repeats identical payloads; only the first should project."""
    calls = {"n": 0}
    orig = control_app.project_state

    def wrapped(ingress):
        calls["n"] += 1
        return orig(ingress)

    monkeypatch.setattr(control_app, "project_state", wrapped)
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r1 = client.post("/api/debug/ingress", json=raw)
    r2 = client.post("/api/debug/ingress", json=raw)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["state_id"] == r2.json()["state_id"]
    assert calls["n"] == 1


def test_manual_command_queue_and_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    assert client.post("/api/debug/ingress", json=raw).status_code == 200

    r0 = client.get("/api/debug/poll_instruction")
    assert r0.status_code == 200
    assert r0.json()["manual_action"] is None

    r_bad = client.post("/api/debug/manual_command", json={})
    assert r_bad.status_code == 400

    snap = client.get("/api/debug/snapshot").json()
    cmd = snap["view_model"]["actions"][0]["command"]

    r1 = client.post("/api/debug/manual_command", json={"command": cmd})
    assert r1.status_code == 200
    assert r1.json()["ok"] is True
    assert r1.json()["command"] == cmd

    r2 = client.get("/api/debug/poll_instruction")
    assert r2.status_code == 200
    assert r2.json()["manual_action"] == cmd
    assert r2.json()["approved_action"] is None
    assert r2.json()["agent_mode"] == "manual"

    r3 = client.get("/api/debug/poll_instruction")
    assert r3.json()["manual_action"] is None


def test_manual_command_rejects_illegal_without_snapshot() -> None:
    r = client.post("/api/debug/manual_command", json={"command": "END"})
    assert r.status_code == 400


def test_manual_command_rejects_not_legal() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    assert client.post("/api/debug/ingress", json=raw).status_code == 200
    r = client.post("/api/debug/manual_command", json={"command": "NOT_A_REAL_CMD"})
    assert r.status_code == 400


def test_agent_hitl_queue_after_resume(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "propose")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r1 = client.post("/api/debug/ingress", json=raw)
    assert r1.status_code == 200
    agent = r1.json().get("agent") or {}
    assert agent.get("pending_approval") is not None
    assert agent.get("awaiting_interrupt") is True

    r2 = client.post("/api/agent/resume", json={"kind": "approve"})
    assert r2.status_code == 200
    assert r2.json().get("pending_approval") is None

    r3 = client.get("/api/debug/poll_instruction")
    assert r3.status_code == 200
    assert r3.json()["manual_action"] is not None


def test_agent_resume_validation() -> None:
    r = client.post("/api/agent/resume", json={"kind": "edit"})
    assert r.status_code == 400


def test_agent_retry_no_ingress() -> None:
    r = client.post("/api/agent/retry")
    assert r.status_code == 400


def test_agent_retry_reruns_on_same_ingress(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "propose")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r1 = client.post("/api/debug/ingress", json=raw)
    assert r1.status_code == 200
    a1 = r1.json().get("agent") or {}
    assert a1.get("pending_approval") is not None

    r2 = client.post("/api/agent/retry")
    assert r2.status_code == 200
    body = r2.json()
    a2 = body.get("agent") or {}
    assert body.get("state_id") == r1.json().get("state_id")
    assert a2.get("pending_approval") is not None


def test_agent_status_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    r = client.get("/api/agent/status")
    assert r.status_code == 200
    assert r.json()["agent_mode"] == "manual"


def test_debug_snapshot_shows_llm_openai_from_env(monkeypatch) -> None:
    """Regression: payload.agent must include proposer/llm_backend (not UI mock/stub fallbacks)."""
    monkeypatch.setenv("SLAY_PROPOSER", "llm")
    monkeypatch.setenv("SLAY_LLM_BACKEND", "openai")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    agent = r.json().get("agent") or {}
    assert agent.get("proposer") == "llm"
    assert agent.get("llm_backend") == "openai"
