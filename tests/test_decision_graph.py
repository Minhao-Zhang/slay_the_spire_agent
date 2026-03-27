from __future__ import annotations

import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.decision_engine.graph import _proposal_hygiene, build_agent_graph

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _cfg(
    thread: str,
    *,
    mode: str = "propose",
    now: float | None = None,
    ttl: float | None = None,
    proposer: str = "mock",
) -> dict:
    c: dict = {
        "configurable": {
            "thread_id": thread,
            "agent_mode": mode,
            "proposer": proposer,
        },
    }
    if now is not None:
        c["configurable"]["now"] = now
    if ttl is not None:
        c["configurable"]["proposal_ttl_seconds"] = ttl
    return c


def test_agent_graph_compiles_with_injected_checkpointer() -> None:
    saver = InMemorySaver()
    graph = build_agent_graph(checkpointer=saver)
    assert graph is not None


def test_manual_mode_no_interrupt() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    graph = build_agent_graph()
    cfg = _cfg("t-manual", mode="manual")
    out = graph.invoke({"ingress_raw": raw}, cfg)
    assert "__interrupt__" not in out
    assert out["proposal"]["status"] == "idle"
    assert out.get("emitted_command") is None
    assert "mode:manual" in (out.get("decision_trace") or [])


def test_auto_mode_executes_without_interrupt() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    graph = build_agent_graph()
    cfg = _cfg("t-auto", mode="auto")
    out = graph.invoke({"ingress_raw": raw}, cfg)
    assert "__interrupt__" not in out
    assert out["proposal"]["status"] == "executed"
    assert out["emitted_command"] is not None
    assert len(out["view_model"]["actions"]) >= 1
    assert out["emitted_command"] == out["view_model"]["actions"][0]["command"]


def test_propose_mode_interrupt_and_approve() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    graph = build_agent_graph()
    cfg = _cfg("t-prop", mode="propose")
    paused = graph.invoke({"ingress_raw": raw}, cfg)
    assert "__interrupt__" in paused
    assert paused["proposal"]["status"] == "awaiting_approval"

    final = graph.invoke(Command(resume={"kind": "approve"}), cfg)
    assert "__interrupt__" not in final
    assert final["proposal"]["status"] == "executed"
    assert final["emitted_command"] == paused["proposal"]["command"]


def test_propose_reject_marks_stale() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    graph = build_agent_graph()
    cfg = _cfg("t-rej", mode="propose")
    graph.invoke({"ingress_raw": raw}, cfg)
    final = graph.invoke(Command(resume="reject"), cfg)
    assert final["proposal"]["status"] == "stale"
    assert final.get("emitted_command") is None


def test_checkpoint_reload_after_propose() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    saver = InMemorySaver()
    graph = build_agent_graph(checkpointer=saver)
    cfg = _cfg("t-reload", mode="propose")
    graph.invoke({"ingress_raw": raw}, cfg)
    graph.invoke(Command(resume={"kind": "approve"}), cfg)
    snap = graph.get_state(cfg)
    assert snap.values["proposal"]["status"] == "executed"


def test_thread_ids_isolate_state() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    graph = build_agent_graph()
    cfg_a = _cfg("a", mode="propose")
    cfg_b = _cfg("b", mode="propose")
    graph.invoke({"ingress_raw": raw}, cfg_a)
    graph.invoke({"ingress_raw": raw}, cfg_b)
    graph.invoke(Command(resume={"kind": "approve"}), cfg_a)
    graph.invoke(Command(resume="reject"), cfg_b)
    assert graph.get_state(cfg_a).values["proposal"]["status"] == "executed"
    assert graph.get_state(cfg_b).values["proposal"]["status"] == "stale"


def test_auto_failure_increments_failure_streak() -> None:
    """No legal actions → mock error; repeat on new state, streak accumulates."""
    graph = build_agent_graph()
    cfg = _cfg("t-streak", mode="auto", now=1.0)
    # main menu projection has no card actions → mock proposal fails
    menu = {
        "in_game": False,
        "ready_for_command": True,
        "available_commands": [],
        "game_state": {},
    }
    r1 = graph.invoke({"ingress_raw": menu}, cfg)
    assert r1["proposal"]["status"] == "error"
    assert r1["failure_streak"] == 1

    r2 = graph.invoke({"ingress_raw": menu}, cfg)
    assert r2["failure_streak"] == 2


def test_hygiene_clears_executed_when_command_not_legal_on_vm() -> None:
    """Avoid showing e.g. reward ``choose 0`` against a combat action list (coarse state_id, stale VM)."""
    state = {
        "state_id": "sid-fixed",
        "view_model": {
            "actions": [{"command": "END"}],
            "combat": {"hand": []},
        },
        "proposal": {
            "status": "executed",
            "for_state_id": "sid-fixed",
            "command": "choose 0",
            "resolve_tag": "shortcut:single_action",
        },
        "decision_trace": [],
        "failure_streak": 0,
    }
    cfg = _cfg("t-hygiene-illegal", mode="auto")
    out = _proposal_hygiene(state, cfg)
    assert out["proposal"]["status"] == "idle"
    assert "reset:executed_not_legal_on_vm" in (out["decision_trace"] or [])


def test_approval_times_out_before_interrupt_when_ttl_negative() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    graph = build_agent_graph()
    cfg = _cfg("t-ttl", mode="propose", now=100.0, ttl=-1.0)
    out = graph.invoke({"ingress_raw": raw}, cfg)
    assert "__interrupt__" not in out
    assert out["proposal"]["status"] == "error"
    assert out["proposal"].get("error_reason") == "approval_timeout"
