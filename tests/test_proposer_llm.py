from __future__ import annotations

import json
from pathlib import Path

from src.domain.play_resolve import token_play_command_for_action
from src.decision_engine.graph import build_agent_graph
from src.decision_engine.proposer import set_llm_gateway_for_tests
from src.llm_gateway.stub import StubLlmGateway

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_auto_lane_uses_llm_proposer_with_fallback() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    from src.domain.contracts import parse_ingress_envelope
    from src.domain.state_projection import project_state

    vm = project_state(parse_ingress_envelope(raw)).model_dump(mode="json", by_alias=True)
    first_cmd = vm["actions"][0]["command"]

    set_llm_gateway_for_tests(
        StubLlmGateway(fixed_response=json.dumps({"command": None, "rationale": "let fallback run"})),
    )
    g = build_agent_graph()
    cfg = {
        "configurable": {
            "thread_id": "llm-proposer-t",
            "agent_mode": "auto",
            "proposer": "llm",
        },
    }
    out = g.invoke({"ingress_raw": raw}, cfg)
    assert out["proposal"]["status"] == "executed"
    assert out["emitted_command"] == first_cmd


def test_auto_lane_llm_proposes_exact_command() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    from src.domain.contracts import parse_ingress_envelope
    from src.domain.state_projection import project_state

    vm = project_state(parse_ingress_envelope(raw)).model_dump(mode="json", by_alias=True)
    play = next(a for a in vm["actions"] if token_play_command_for_action(a))
    target = token_play_command_for_action(play)
    assert target is not None
    canonical = str(play["command"])

    set_llm_gateway_for_tests(
        StubLlmGateway(
            fixed_response=json.dumps({"command": target, "rationale": "stub pick"}),
        ),
    )
    g = build_agent_graph()
    cfg = {
        "configurable": {
            "thread_id": "llm-proposer-t2",
            "agent_mode": "auto",
            "proposer": "llm",
        },
    }
    out = g.invoke({"ingress_raw": raw}, cfg)
    assert out["emitted_command"] == canonical
