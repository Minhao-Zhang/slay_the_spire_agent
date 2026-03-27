"""Seed-based LangGraph thread_id and HITL / menu routing."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from src.control_api.app import app

client = TestClient(app)
_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_step_ingress_uses_run_prefix_from_seed(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r = client.post("/api/debug/ingress", json=raw)
    assert r.status_code == 200
    agent = r.json().get("agent") or {}
    assert agent.get("thread_id") == "run-4242424242424242"
    assert agent.get("run_seed") == "4242424242424242"


def test_pending_hitl_pins_thread_when_ingress_maps_to_menu(monkeypatch) -> None:
    """Menu-shaped ingress while HITL is open uses the interrupt thread for ``invoke`` (trace rows)."""
    monkeypatch.setenv("SLAY_AGENT_MODE", "propose")
    monkeypatch.setenv("SLAY_TRACE_BACKEND", "memory")
    combat = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    r1 = client.post("/api/debug/ingress", json=combat)
    assert r1.status_code == 200
    agent1 = r1.json().get("agent") or {}
    assert agent1.get("awaiting_interrupt") is True
    game_tid = agent1.get("thread_id")
    assert game_tid == "run-4242424242424242"

    menu = json.loads((_FIXTURES / "ingress_menu.json").read_text(encoding="utf-8"))
    r2 = client.post("/api/debug/ingress", json=menu)
    assert r2.status_code == 200
    agent2 = r2.json().get("agent") or {}
    assert agent2.get("thread_id") == game_tid

    tr = client.get("/api/debug/trace", params={"thread_id": game_tid})
    assert tr.status_code == 200
    assert tr.json()["count"] >= 2
    assert all(e.get("thread_id") == game_tid for e in tr.json()["events"])
    menu_only = client.get("/api/debug/trace", params={"thread_id": "run-menu"}).json()["events"]
    assert len(menu_only) == 0


def test_resume_after_menu_shaped_ingress(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "propose")
    combat = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    assert client.post("/api/debug/ingress", json=combat).status_code == 200
    menu = json.loads((_FIXTURES / "ingress_menu.json").read_text(encoding="utf-8"))
    assert client.post("/api/debug/ingress", json=menu).status_code == 200
    r = client.post("/api/agent/resume", json={"kind": "approve"})
    assert r.status_code == 200
    assert r.json().get("pending_approval") is None


def test_two_seeds_isolate_step_seq(monkeypatch) -> None:
    monkeypatch.setenv("SLAY_AGENT_MODE", "manual")
    monkeypatch.setenv("SLAY_TRACE_BACKEND", "memory")
    a = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    a1 = {**a, "game_state": {**a["game_state"], "seed": 111}}
    a2 = {**a, "game_state": {**a["game_state"], "seed": 222}}
    assert client.post("/api/debug/ingress", json=a1).status_code == 200
    assert client.post("/api/debug/ingress", json=a2).status_code == 200
    t1 = client.get("/api/debug/trace", params={"thread_id": "run-111"}).json()
    t2 = client.get("/api/debug/trace", params={"thread_id": "run-222"}).json()
    assert t1["count"] == 1
    assert t2["count"] == 1
    assert t1["events"][-1]["step_seq"] == 1
    assert t2["events"][-1]["step_seq"] == 1
