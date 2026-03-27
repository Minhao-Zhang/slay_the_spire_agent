from __future__ import annotations

import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.runnables import RunnableConfig

from src.domain.contracts.ingress import parse_ingress_envelope
from src.domain.play_resolve import token_play_command_for_action
from src.domain.state_projection import project_state
from src.decision_engine.command_queue import drain_command_queue_if_ready
from src.decision_engine.graph import build_agent_graph
from src.decision_engine.proposer import set_llm_gateway_for_tests
from src.llm_gateway.stub import StubLlmGateway

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_drain_requires_combat() -> None:
    cfg: RunnableConfig = {"configurable": {"agent_mode": "auto", "thread_id": "t"}}
    state = {
        "command_queue": ["END"],
        "view_model": {"actions": [{"command": "END"}], "combat": None},
        "decision_trace": [],
    }
    out = drain_command_queue_if_ready(state, cfg)
    assert out.get("command_queue") == []


def test_drain_emits_legal_head() -> None:
    cfg: RunnableConfig = {"configurable": {"agent_mode": "auto", "thread_id": "t"}}
    state = {
        "command_queue": ["END", "END"],
        "view_model": {
            "actions": [{"command": "END"}],
            "combat": {"monsters": []},
        },
        "decision_trace": [],
    }
    out = drain_command_queue_if_ready(state, cfg)
    assert out["emitted_command"] == "END"
    assert out["command_queue"] == ["END"]


def test_auto_llm_multi_command_queues_then_drains() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    vm = project_state(parse_ingress_envelope(raw)).model_dump(mode="json", by_alias=True)
    play_tok = None
    canon_play = None
    for a in vm["actions"]:
        t = token_play_command_for_action(a)
        if t:
            play_tok = t
            canon_play = a["command"]
            break
    assert play_tok and canon_play
    set_llm_gateway_for_tests(
        StubLlmGateway(
            fixed_response=json.dumps(
                {
                    "commands": [play_tok, "END"],
                    "rationale": "combo",
                },
            ),
        ),
    )
    try:
        g = build_agent_graph(checkpointer=InMemorySaver())
        cfg: RunnableConfig = {
            "configurable": {
                "thread_id": "t-mc",
                "agent_mode": "auto",
                "proposer": "llm",
            },
        }
        out1 = g.invoke({"ingress_raw": raw}, cfg)
        assert out1["proposal"]["status"] == "executed"
        assert out1["emitted_command"] == canon_play
        assert out1.get("command_queue") == ["END"]

        out2 = g.invoke({"ingress_raw": raw}, cfg)
        assert out2["emitted_command"] == "END"
        assert out2.get("command_queue") in (None, [], ())
    finally:
        set_llm_gateway_for_tests(None)


def test_manual_skips_drain() -> None:
    cfg: RunnableConfig = {"configurable": {"agent_mode": "manual", "thread_id": "t"}}
    state = {
        "command_queue": ["END"],
        "view_model": {
            "actions": [{"command": "END"}],
            "combat": {"monsters": []},
        },
        "decision_trace": [],
    }
    assert drain_command_queue_if_ready(state, cfg) == {}
