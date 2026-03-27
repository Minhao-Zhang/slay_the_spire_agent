from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.replay import (
    compute_replay_metrics,
    replay_ingress_only,
    replay_with_resume,
)
from src.trace_telemetry.store import InMemoryTraceStore

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _combat_cfg(**kwargs):
    base = {
        "thread_id": "replay-ci",
        "agent_mode": "auto",
        "proposer": "mock",
        "memory_max_turns": 32,
        "now": 1_700_000_000.0,
    }
    base.update(kwargs)
    return {"configurable": base}


def test_golden_replay_is_deterministic() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    cfg = _combat_cfg()
    s1 = InMemoryTraceStore()
    s2 = InMemoryTraceStore()
    replay_ingress_only(ingress_bodies=[raw], cfg=cfg, trace_store=s1)
    replay_ingress_only(ingress_bodies=[raw], cfg=cfg, trace_store=s2)
    assert s1.list_events() == s2.list_events()


def test_replay_metrics_thresholds_auto_execute() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    st = InMemoryTraceStore()
    replay_ingress_only(ingress_bodies=[raw, raw], cfg=_combat_cfg(), trace_store=st)
    m = compute_replay_metrics(st.list_events())
    assert m.steps == 2
    assert m.ingress_steps == 2
    assert m.emitted_commands == 2
    assert m.proposal_terminal_executed >= 1


def test_replay_hitl_produces_resume_step() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    st = InMemoryTraceStore()
    cfg = _combat_cfg(agent_mode="propose")
    _, raws = replay_with_resume(
        ingress_body=raw,
        resume_payload={"kind": "approve"},
        cfg=cfg,
        trace_store=st,
    )
    events = st.list_events()
    assert len(events) == 2
    assert events[0]["step_kind"] == "ingress"
    assert events[0]["awaiting_interrupt"] is True
    assert events[1]["step_kind"] == "resume"
    assert events[1]["resume_kind"] == "approve"
    assert raws[-1].get("emitted_command")
