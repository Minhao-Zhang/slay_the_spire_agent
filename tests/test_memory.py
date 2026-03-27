from __future__ import annotations

import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.decision_engine.graph import build_agent_graph
from src.memory.runtime import get_app_memory_store, reset_app_memory_store_for_tests
from src.memory.store import InMemoryMemoryStore

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_in_memory_store_namespace_isolation() -> None:
    s = InMemoryMemoryStore()
    s.put(("strategy", "A"), "k", {"v": 1})
    s.put(("strategy", "B"), "k", {"v": 2})
    assert s.get(("strategy", "A"), "k") == {"v": 1}
    assert s.get(("strategy", "B"), "k") == {"v": 2}


def test_memory_log_bounded_per_config() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    g = build_agent_graph(checkpointer=InMemorySaver())
    cfg = {
        "configurable": {
            "thread_id": "mem-bound",
            "agent_mode": "manual",
            "proposer": "mock",
            "memory_max_turns": 4,
        },
    }
    for _ in range(10):
        g.invoke({"ingress_raw": raw}, cfg)
    snap = g.get_state(cfg)
    log = snap.values.get("memory_log") or []
    assert len(log) == 4
    assert log[-1].get("seq") == 10
    assert log[0].get("seq") == 7


def test_checkpoint_retains_memory_across_invocations() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    g = build_agent_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "mem-retain", "agent_mode": "manual"}}
    g.invoke({"ingress_raw": raw}, cfg)
    g.invoke({"ingress_raw": raw}, cfg)
    log = g.get_state(cfg).values.get("memory_log") or []
    assert len(log) == 2


def test_propose_resume_does_not_append_extra_memory_row() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    g = build_agent_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "mem-resume", "agent_mode": "propose"}}
    g.invoke({"ingress_raw": raw}, cfg)
    mid = len(g.get_state(cfg).values.get("memory_log") or [])
    assert mid == 1
    g.invoke(Command(resume={"kind": "approve"}), cfg)
    log = g.get_state(cfg).values.get("memory_log") or []
    assert len(log) == 1


def test_strategy_store_receives_class_namespace() -> None:
    reset_app_memory_store_for_tests()
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    g = build_agent_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "mem-store", "agent_mode": "manual"}}
    g.invoke({"ingress_raw": raw}, cfg)
    st = get_app_memory_store().get(("strategy", "IRONCLAD", "mem-store"), "last_turn")
    assert st is not None
    assert "state_id" in st
