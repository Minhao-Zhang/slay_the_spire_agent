from __future__ import annotations

import json
from pathlib import Path

from src.domain.legal_command import is_command_legal
from src.decision_engine.proposal_logic import (
    apply_hygiene_on_proposal,
    finalize_approval,
    mock_propose_command,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_mock_propose_first_action() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    from src.domain.contracts import parse_ingress_envelope
    from src.domain.state_projection import project_state

    vm = project_state(parse_ingress_envelope(raw)).model_dump(mode="json", by_alias=True)
    cmd, why = mock_propose_command(vm)
    assert cmd
    assert cmd == vm["actions"][0]["command"]


def test_hygiene_stale_when_state_advances() -> None:
    p = {
        "status": "awaiting_approval",
        "for_state_id": "old",
        "command": "END",
        "expires_at": 999.0,
    }
    out, trace = apply_hygiene_on_proposal(state_id="new", proposal=p, now=1.0)
    assert out["status"] == "stale"
    assert "stale:state_id_changed" in trace


def test_hygiene_timeout() -> None:
    p = {
        "status": "awaiting_approval",
        "for_state_id": "s",
        "command": "END",
        "expires_at": 10.0,
    }
    out, trace = apply_hygiene_on_proposal(state_id="s", proposal=p, now=11.0)
    assert out["status"] == "error"
    assert out["error_reason"] == "approval_timeout"


def test_finalize_approve() -> None:
    raw = json.loads((_FIXTURES / "ingress_combat.json").read_text(encoding="utf-8"))
    from src.domain.contracts import compute_state_id, parse_ingress_envelope
    from src.domain.state_projection import project_state

    ing = parse_ingress_envelope(raw)
    sid = compute_state_id(ing)
    vm = project_state(ing).model_dump(mode="json", by_alias=True)
    prop = {
        "status": "awaiting_approval",
        "for_state_id": sid,
        "command": vm["actions"][0]["command"],
    }
    p2, emitted, trace = finalize_approval(
        current_state_id=sid,
        view_model=vm,
        proposal=prop,
        resume={"kind": "approve"},
    )
    assert p2["status"] == "executed"
    assert emitted == prop["command"]
    assert "executed:approved" in trace


def test_finalize_stale_when_state_mismatch() -> None:
    prop = {"status": "awaiting_approval", "for_state_id": "a", "command": "END"}
    p2, emitted, trace = finalize_approval(
        current_state_id="b",
        view_model={"actions": [{"command": "END"}]},
        proposal=prop,
        resume={"kind": "approve"},
    )
    assert p2["status"] == "stale"
    assert emitted is None


def test_finalize_edit_legal() -> None:
    vm = {"actions": [{"command": "END"}, {"command": "PLAY 0"}]}
    sid = "x"
    prop = {"status": "awaiting_approval", "for_state_id": sid, "command": "END"}
    p2, emitted, trace = finalize_approval(
        current_state_id=sid,
        view_model=vm,
        proposal=prop,
        resume={"kind": "edit", "command": "PLAY 0"},
    )
    assert p2["status"] == "executed"
    assert emitted == "PLAY 0"


def test_is_command_legal_normalizes_space() -> None:
    vm = {"actions": [{"command": "play 0"}]}
    assert is_command_legal(vm, "PLAY  0")
